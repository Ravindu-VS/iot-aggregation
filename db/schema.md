# DynamoDB Schema (Starter)

Table: iot_uploads

Primary key:
- data_id (string, HASH)

Recommended attributes:
- sensor_id (string)
- object_key (string)
- status (string: pending|processing|done|failed)
- summary (map)
- timestamp (ISO-8601 string)

Owner: Database Administrator
