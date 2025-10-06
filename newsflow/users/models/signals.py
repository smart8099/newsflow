"""
Signal handlers for users app.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .profile import UserProfile
from .user import User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is saved."""
    if hasattr(instance, "profile"):
        instance.profile.save()
