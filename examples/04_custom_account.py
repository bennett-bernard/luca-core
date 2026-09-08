"""Extend Account through inheritance and use caller-defined metadata."""

from pydantic import Field, ValidationError

from lumbago import Account, AccountType, CrudService, InMemoryRepository


class DepartmentAccount(Account):
    """An application-specific account with an additional validated field."""

    department_code: str = Field(min_length=2, max_length=12)

    def display_label(self) -> str:
        """Return an application-specific display label."""

        return f"{self.department_code}: {self.code} - {self.name}"


def main() -> None:
    """Show declared extensions, metadata, freezing, and defensive copies."""

    accounts = CrudService(InMemoryRepository(DepartmentAccount))
    account = accounts.create(
        DepartmentAccount(
            code="6100",
            name="Engineering Software",
            account_type=AccountType.EXPENSE,
            department_code="ENG",
            metadata={"source": {"system": "custom-app"}},
        )
    )

    print(account.display_label())
    print(f"Metadata: {account.metadata}")

    try:
        account.name = "Changed without the service"
    except ValidationError as error:
        print(f"\nFrozen model rejected assignment:\n  {error}")

    source = account.metadata["source"]
    assert isinstance(source, dict)
    source["system"] = "mutated-by-caller"
    print(f"\nCaller's mutated metadata: {account.metadata}")
    print(f"Repository's protected copy: {accounts.retrieve(account.id).metadata}")

    updated = accounts.update(account.id, {"department_code": "OPS"})
    print(f"\nValidated service update: {updated.display_label()}")


if __name__ == "__main__":
    main()
