from database import get_connection

conn = get_connection()

rows = conn.execute("""
    SELECT id, medicine_name, expiry_date,
           date(expiry_date) AS parsed_date
    FROM medicines
""").fetchall()

for row in rows:
    print(dict(row))

conn.close()