"""A project invitation, never a matching email/name, establishes membership."""
from sqlalchemy import select
from .models import CustomerMembership, IntakeLink


def connect_project(db, account_id, link):
    membership = db.scalar(select(CustomerMembership).where(
        CustomerMembership.account_id == account_id, CustomerMembership.project_id == link.project_id))
    if membership:
        previous = db.get(IntakeLink, membership.link_id)
        if not link.revoked_at or previous.revoked_at:
            membership.link_id = link.id
    else:
        membership = CustomerMembership(account_id=account_id, project_id=link.project_id, link_id=link.id)
        db.add(membership)
    return membership
