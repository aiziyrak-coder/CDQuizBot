from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Test(Base):
    __tablename__ = 'tests'
    
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=False)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    questions = relationship("Question", back_populates="test", cascade="all, delete-orphan")
    results = relationship("TestResult", back_populates="test", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.id'), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    
    test = relationship("Test", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = 'answers'
    
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    answer_letter = Column(String(1), nullable=False)  # A, B, C, D, etc.
    
    question = relationship("Question", back_populates="answers")


class TestResult(Base):
    __tablename__ = 'test_results'
    
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=False)
    correct_answers = Column(Integer, default=0)
    wrong_answers = Column(Integer, default=0)
    skipped_answers = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)
    best_score = Column(Integer, default=0)
    best_correct = Column(Integer, default=0)
    best_wrong = Column(Integer, default=0)
    best_skipped = Column(Integer, default=0)
    best_duration = Column(Integer, default=0)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    test = relationship("Test", back_populates="results")
    user_answers = relationship("UserAnswer", back_populates="test_result", cascade="all, delete-orphan")


class UserAnswer(Base):
    __tablename__ = 'user_answers'
    
    id = Column(Integer, primary_key=True)
    test_result_id = Column(Integer, ForeignKey('test_results.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer_id = Column(Integer, ForeignKey('answers.id'), nullable=True)
    is_correct = Column(Boolean, default=False)
    is_skipped = Column(Boolean, default=False)
    
    test_result = relationship("TestResult", back_populates="user_answers")


class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=False)
    amount = Column(Float, nullable=False)
    expected_amount = Column(Float, nullable=False)  # Amount with random last 2 digits
    screenshot_path = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, nullable=True)  # Admin telegram_id
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TestAccess(Base):
    """Track which tests user has paid for"""
    __tablename__ = 'test_access'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=False)
    test_id = Column(Integer, ForeignKey('tests.id'), nullable=False)
    paid_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)  # Link to payment record
    
    # Ensure one access per user per test
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class Database:
    def __init__(self, db_path='bot.db'):
        self.db_path = db_path
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}', echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
    
    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def get_session(self):
        async with self.async_session() as session:
            yield session

db = Database()
