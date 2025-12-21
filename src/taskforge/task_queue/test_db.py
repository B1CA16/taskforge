from src.taskforge.task_queue.db import engine
from src.taskforge.task_queue.models import Base

# Creates all tables
Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
