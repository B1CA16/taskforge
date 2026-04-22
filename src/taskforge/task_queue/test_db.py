from taskforge.db.base import engine
from taskforge.task_queue.models import Base

# Drops all tables and then creates them
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
