from db.database import create_table_if_not_exists


def create_table():
    create_table_if_not_exists()
    print("Table is ready.")


if __name__ == "__main__":
    create_table()