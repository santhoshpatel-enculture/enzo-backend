import asyncio
import json
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect():
    client = AsyncIOMotorClient("mongodb+srv://vishnu:Vishnu123@developmentcluster.lu9ej3j.mongodb.net/")
    db = client["enzo_db"]
    user = await db.users.find_one({"email": "santhosh@enculture.ai"})
    if user:
        print(json.dumps(user, default=json_util.default, indent=2))
    else:
        print("santhosh@enculture.ai NOT found!")

asyncio.run(inspect())
