"""A project invitation, never a matching email/name, establishes membership."""
from fastapi import HTTPException
from sqlalchemy import select
from .models import CustomerMembership, IntakeLink


def connect_project(db, account_id, link):
    membership = db.scalar(select(CustomerMembership).where(
        CustomerMembership.account_id == account_id, CustomerMembership.project_id == link.project_id))
    if membership and membership.revoked_at:
        raise HTTPException(403, 'Your project access was removed. Ask the workspace owner to restore it.')
    if membership:
        previous = db.get(IntakeLink, membership.link_id)
        if not link.revoked_at or previous.revoked_at:
            membership.link_id = link.id
    else:
        from .models import Project
        if db.get(Project, link.project_id).customer_access == 'members':
            raise HTTPException(403, 'Ask the workspace owner to add your account to this project.')
        membership = CustomerMembership(account_id=account_id, project_id=link.project_id, link_id=link.id)
        db.add(membership)
    return membership
