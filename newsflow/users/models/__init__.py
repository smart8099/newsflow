"""
Models package for users app.
Imports all models for backward compatibility.
"""

# Import signals to ensure they are registered
from . import signals
from .profile import UserProfile
from .user import User

__all__ = [
    "User",
    "UserProfile",
]
