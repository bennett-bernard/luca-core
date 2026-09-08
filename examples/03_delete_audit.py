"""Hard-delete a record while retaining its audit event."""

from lumbago import (
    Account,
    AccountService,
    AccountType,
    InMemoryAuditLog,
    InMemoryRepository,
    RecordNotFoundError,
)


def main() -> None:
    """Show deletion and the resulting immutable audit record."""

    audit_log = InMemoryAuditLog()
    accounts = AccountService(
        InMemoryRepository(Account),
        audit_log=audit_log,
    )
    account = accounts.create(
        Account(
            code="TEMP",
            name="Temporary Account",
            account_type=AccountType.EXPENSE,
            metadata={"reason": "audit demonstration"},
        )
    )

    deleted = accounts.delete(account.id, actor="example-user")
    print(f"Deleted {deleted.code} ({deleted.id})")

    try:
        accounts.retrieve(account.id)
    except RecordNotFoundError as error:
        print(f"Retrieval after deletion: {error}")

    print("\nAudit event retained after deletion:")
    print(accounts.list_audit_events()[0].model_dump_json(indent=2))


if __name__ == "__main__":
    main()
