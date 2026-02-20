from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Build connection args
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Verify connections before use
)

# Optimize SQLite for performance
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # WAL mode for better concurrent performance
        cursor.execute("PRAGMA journal_mode=WAL")
        # Normal sync - much faster than FULL, still safe
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Increase cache size (negative = KB, so -64000 = 64MB)
        cursor.execute("PRAGMA cache_size=-64000")
        # Store temp tables in memory
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Enable memory-mapped I/O (256MB)
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app.models import rule, user, audit
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    from app.models.user import User
    from app.services.auth_service import get_password_hash
    
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
    
    db.close()