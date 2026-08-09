"""`PostgresAccountStore` -- the durable path for `src/adapters/identity_store.py`'s
`AccountStore` protocol, the same split `PostgresBookingStore` makes for bookings.

`account_profiles.canonical` is the only thing a profile is rebuilt from (D-006's
dual-storage shape). Everything else is projected columns, because everything else is
something a query actually filters on.

The one thing worth reading twice is `verify_otp`: it deletes the challenge *before*
creating the account, so a double-submitted login cannot mint two tokens off one challenge,
and it catches `IntegrityError` on the account insert so a genuine race lands on the
`UNIQUE (email, role)` constraint rather than becoming a duplicate row -- the same backstop
posture `PostgresBookingStore.insert` takes for idempotency keys.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import AccountProfileRow, AccountRow, AuthTokenRow, OtpChallengeRow
from src.adapters.identity_store import (
    CHALLENGE_TTL_MINUTES,
    OtpChallenge,
    OtpChallengeError,
    build_account,
    build_profile,
    mint_token_value,
    normalise_email,
)
from src.domain.identity import (
    TOKEN_TTL_HOURS,
    Account,
    AccountRole,
    AuthToken,
    BuyerProfile,
    SellerProfile,
    is_demo_otp,
)


class PostgresAccountStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def request_otp(
        self, *, email: str, role: AccountRole, now: datetime | None = None
    ) -> OtpChallenge:
        moment = now or datetime.now(UTC)
        normalised = normalise_email(email)
        expires_at = moment + timedelta(minutes=CHALLENGE_TTL_MINUTES)

        async with self._sessions() as session:
            row = await session.get(OtpChallengeRow, (normalised, role.value))
            if row is None:
                session.add(
                    OtpChallengeRow(
                        email=normalised,
                        role=role.value,
                        issued_at=moment,
                        expires_at=expires_at,
                    )
                )
            else:
                # Re-requesting extends the window rather than stacking a second row --
                # "resend the code" is an ordinary thing to click twice.
                row.issued_at = moment
                row.expires_at = expires_at
            await session.commit()

        return OtpChallenge(email=normalised, role=role, issued_at=moment, expires_at=expires_at)

    async def verify_otp(
        self,
        *,
        email: str,
        role: AccountRole,
        code: str,
        full_name: str,
        phone: str,
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        moment = now or datetime.now(UTC)
        normalised = normalise_email(email)

        async with self._sessions() as session:
            challenge = await session.get(OtpChallengeRow, (normalised, role.value))
            if challenge is None:
                raise OtpChallengeError("no challenge was issued for this email/role")
            expired = moment >= challenge.expires_at
            if expired or not is_demo_otp(code):
                if expired:
                    await session.delete(challenge)
                    await session.commit()
                raise OtpChallengeError("challenge expired" if expired else "code did not match")
            # Single-use, and consumed before anything else can fail -- a retried submit
            # finds no challenge rather than minting a second token off the same one.
            await session.delete(challenge)
            await session.commit()

        return await self._find_or_create(
            email=normalised,
            role=role,
            full_name=full_name,
            phone=phone,
            profile_fields=profile_fields,
            now=moment,
        )

    async def sign_in_external(
        self,
        *,
        email: str,
        role: AccountRole,
        full_name: str,
        phone: str = "",
        profile_fields: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> tuple[Account, AuthToken, bool]:
        # No challenge to consume -- Google already proved the address. Same account path
        # from here on, so Google and email sign-in land on one account, not two.
        return await self._find_or_create(
            email=normalise_email(email),
            role=role,
            full_name=full_name,
            phone=phone,
            profile_fields=profile_fields,
            now=now or datetime.now(UTC),
        )

    async def claim_dealership(self, account_id: uuid.UUID, dealer_id: uuid.UUID) -> SellerProfile:
        async with self._sessions() as session:
            row = await session.get(AccountProfileRow, account_id)
            if row is None or row.role != AccountRole.SELLER.value:
                raise ValueError("no seller profile for that account")
            profile = SellerProfile.model_validate(row.canonical)
            if profile.dealer_id is not None:
                raise ValueError("this account already has a dealership")
            claimed = profile.model_copy(update={"dealer_id": dealer_id})
            row.canonical = claimed.model_dump(mode="json")
            await session.commit()
        return claimed

    async def _find_or_create(
        self,
        *,
        email: str,
        role: AccountRole,
        full_name: str,
        phone: str,
        profile_fields: dict[str, object] | None,
        now: datetime,
    ) -> tuple[Account, AuthToken, bool]:
        normalised, moment = normalise_email(email), now
        account = await self.find_account(email=normalised, role=role)
        created = False
        if account is None:
            account = build_account(
                email=normalised, role=role, full_name=full_name, phone=phone, now=moment
            )
            profile = build_profile(account, profile_fields)
            async with self._sessions() as session:
                session.add(
                    AccountRow(
                        id=account.id,
                        role=account.role.value,
                        email=account.email,
                        full_name=account.full_name,
                        phone=account.phone,
                        created_at=account.created_at,
                    )
                )
                try:
                    # Flush the account before adding the profile. These two tables are
                    # joined by a plain `ForeignKey` with no `relationship()` between the
                    # mappers, so SQLAlchemy has no dependency edge to sort the unit of work
                    # by and is free to emit the `account_profiles` INSERT first -- which it
                    # does, and which the FK then rejects. Declaring a relationship purely to
                    # fix ordering would add lazy-load machinery nothing here wants; one
                    # explicit flush says the same thing and says it locally.
                    await session.flush()
                    session.add(
                        AccountProfileRow(
                            account_id=account.id,
                            role=account.role.value,
                            canonical=profile.model_dump(mode="json"),
                        )
                    )
                    await session.commit()
                    created = True
                except IntegrityError:
                    # Lost a race to a concurrent first login on the same (email, role).
                    await session.rollback()
                    existing = await self.find_account(email=normalised, role=role)
                    if existing is None:
                        raise
                    account = existing

        return account, await self._issue_token(account, moment), created

    async def _issue_token(self, account: Account, now: datetime) -> AuthToken:
        token = AuthToken(
            token=mint_token_value(),
            account_id=account.id,
            role=account.role,
            issued_at=now,
            expires_at=now + timedelta(hours=TOKEN_TTL_HOURS),
        )
        async with self._sessions() as session:
            session.add(
                AuthTokenRow(
                    token=token.token,
                    account_id=token.account_id,
                    role=token.role.value,
                    issued_at=token.issued_at,
                    expires_at=token.expires_at,
                )
            )
            await session.commit()
        return token

    async def get_account(self, account_id: uuid.UUID) -> Account | None:
        async with self._sessions() as session:
            row = await session.get(AccountRow, account_id)
        return _to_account(row) if row is not None else None

    async def find_account(self, *, email: str, role: AccountRole) -> Account | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AccountRow).where(
                    AccountRow.email == normalise_email(email),
                    AccountRow.role == role.value,
                )
            )
        return _to_account(row) if row is not None else None

    async def get_buyer_profile(self, account_id: uuid.UUID) -> BuyerProfile | None:
        row = await self._profile_row(account_id, AccountRole.BUYER)
        return BuyerProfile.model_validate(row.canonical) if row is not None else None

    async def get_seller_profile(self, account_id: uuid.UUID) -> SellerProfile | None:
        row = await self._profile_row(account_id, AccountRole.SELLER)
        return SellerProfile.model_validate(row.canonical) if row is not None else None

    async def _profile_row(
        self, account_id: uuid.UUID, role: AccountRole
    ) -> AccountProfileRow | None:
        async with self._sessions() as session:
            row = await session.get(AccountProfileRow, account_id)
        return row if row is not None and row.role == role.value else None

    async def resolve_token(self, token: str, *, now: datetime | None = None) -> AuthToken | None:
        moment = now or datetime.now(UTC)
        async with self._sessions() as session:
            row = await session.get(AuthTokenRow, token)
            if row is None:
                return None
            if moment >= row.expires_at:
                await session.delete(row)
                await session.commit()
                return None
            return _to_token(row)

    async def revoke_token(self, token: str) -> None:
        async with self._sessions() as session:
            await session.execute(delete(AuthTokenRow).where(AuthTokenRow.token == token))
            await session.commit()


def _to_account(row: AccountRow) -> Account:
    return Account(
        id=row.id,
        role=AccountRole(row.role),
        email=row.email,
        full_name=row.full_name,
        phone=row.phone,
        created_at=row.created_at,
    )


def _to_token(row: AuthTokenRow) -> AuthToken:
    return AuthToken(
        token=row.token,
        account_id=row.account_id,
        role=AccountRole(row.role),
        issued_at=row.issued_at,
        expires_at=row.expires_at,
    )
