import boto3

# Connect to DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Select your table (use your exact table name)
table = dynamodb.Table('iot_data')

# Insert data
table.put_item(
    Item={
         "data_id": "UUID",
  "sensor_id": "sensor_1",
  "object_key": "uploads/file1.json",
  "status": "pending",
  "summary": {
    "min": 20,
    "max": 35,
    "avg": 27
  },
  "timestamp": "2026-04-11T10:00:00"
    }
)

print("Data inserted successfully!")