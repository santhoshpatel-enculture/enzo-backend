import asyncio
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

async def update_credentials():
    client = AsyncIOMotorClient("mongodb+srv://vishnu:Vishnu123@developmentcluster.lu9ej3j.mongodb.net/")
    db = client["enzo_db"]
    
    # Hash password "Test@1234"
    pwd = b"Test@1234"
    salt = bcrypt.gensalt(10)
    hashed_pwd = bcrypt.hashpw(pwd, salt).decode('utf-8')
    print("Generated hash for Test@1234:", hashed_pwd)
    
    # Update admin@enculture.ai
    res_admin = await db.users.update_one(
        {"email": "admin@enculture.ai"},
        {"$set": {"password": hashed_pwd}}
    )
    print("Update admin@enculture.ai password directly:")
    print("Match count:", res_admin.matched_count)
    print("Modified count:", res_admin.modified_count)

    # Update santhosh@enculture.ai just in case
    res_santhosh = await db.users.update_one(
        {"email": "santhosh@enculture.ai"},
        {"$set": {"password": hashed_pwd}}
    )
    print("Update santhosh@enculture.ai password directly:")
    print("Match count:", res_santhosh.matched_count)
    print("Modified count:", res_santhosh.modified_count)

asyncio.run(update_credentials())
