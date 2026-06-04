import asyncio
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

async def update_password():
    client = AsyncIOMotorClient("mongodb+srv://vishnu:Vishnu123@developmentcluster.lu9ej3j.mongodb.net/")
    db = client["enzo_db"]
    
    # Hash password "Enzo@2024"
    pwd = b"Enzo@2024"
    salt = bcrypt.gensalt(10)
    hashed_pwd = bcrypt.hashpw(pwd, salt).decode('utf-8')
    print("Generated hash:", hashed_pwd)
    
    # Update user in DB
    res = await db.users.update_one(
        {"email": "santhosh@enculture.ai"},
        {"$set": {"password": hashed_pwd}}
    )
    print("Match count:", res.matched_count)
    print("Modified count:", res.modified_count)

asyncio.run(update_password())
