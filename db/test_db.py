from db.database import (
	get_record,
	insert_record,
	list_records,
	update_record_status,
	update_record_summary,
)


def run_manual_smoke_test():
	insert_record("1", "sensor_A", "file1.json")
	update_record_status("1", "processing")
	update_record_summary("1", {"min": 10, "max": 30, "avg": 20})
	print(get_record("1"))
	print(list_records())


if __name__ == "__main__":
	run_manual_smoke_test()