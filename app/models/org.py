"""Org hierarchy API schemas."""

from pydantic import BaseModel


class OrgPersonSummary(BaseModel):
    id: str
    userId: str | None = None
    email: str
    firstName: str
    lastName: str
    designation: str
    department: str
    managerId: str | None = None


class OrgReporteesResponse(BaseModel):
    reportees: list[OrgPersonSummary]
    total: int


class OrgTreeNode(BaseModel):
    id: str
    userId: str | None = None
    label: str
    email: str = ""
    designation: str
    department: str
    managerId: str | None = None
    children: list["OrgTreeNode"] = []


OrgTreeNode.model_rebuild()


class OrgTreeResponse(BaseModel):
    roots: list[OrgTreeNode]
    scope: str
    nodeCount: int
    focalUserId: str | None = None
