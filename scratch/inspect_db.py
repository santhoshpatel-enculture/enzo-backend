import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect():
    client = AsyncIOMotorClient("mongodb+srv://vishnu:Vishnu123@developmentcluster.lu9ej3j.mongodb.net/")
    db = client["enzo_db"]
    cursor = db.users.find({}, {"email": 1, "password": 1, "passwordHash": 1})
    users = await cursor.to_list(100)
    print(f"Total users found: {len(users)}")
    for u in users:
        p = u.get("password")
        ph = u.get("passwordHash")
        print(f"Email: {u.get('email')} | password: {p} ({type(p)}) | passwordHash: {ph} ({type(ph)})")

asyncio.run(inspect())
