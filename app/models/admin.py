"""Admin API Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class AdminUserOut(BaseModel):
    id: str
    email: str
    firstName: str
    lastName: str
    department: str
    designation: str
    location: str = ""
    team: str = ""
    gender: str = ""
    age: int | None = None
    role: str = "Employee"
    tenantId: str | None = None
    tenantName: str | None = None
    managerId: str | None = None
    managerName: str | None = None
    userId: str | None = None
    createdAt: datetime | None = None


class AdminUserFilterOptions(BaseModel):
    tenants: list[dict] = []
    departments: list[str] = []
    teams: list[str] = []
    genders: list[str] = []
    roles: list[str] = []
    managers: list[str] = []


class AdminUsersListResponse(BaseModel):
    users: list[AdminUserOut]
    filterOptions: AdminUserFilterOptions
    total: int
    totalInDatabase: int = 0
    dummyUserCount: int = 0


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    firstName: str
    lastName: str
    department: str = ""
    designation: str = ""
    role: str = "Employee"
    tenantId: str | None = None


class AdminUserUpdate(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    department: str | None = None
    designation: str | None = None
    role: str | None = None
    tenantId: str | None = None
    adminRole: str | None = None
    adminTenantIds: list[str] | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


class TenantBudgetOut(BaseModel):
    tenantId: str
    monthlyTokenLimit: int = 0
    monthlyCostUsdLimit: float = 0.0
    alertThresholdPct: int = 80
    usageTokens: int = 0
    usageCostUsd: float = 0.0


class TenantBudgetUpdate(BaseModel):
    monthlyTokenLimit: int | None = None
    monthlyCostUsdLimit: float | None = None
    alertThresholdPct: int | None = None


class FeedbackSummaryRow(BaseModel):
    tenantId: str
    up: int
    down: int
    total: int


class TenantBreakdownItem(BaseModel):
    tenantId: str
    name: str
    users: int
    tasks: int = 0
    conversations: int
    userMessages: int = 0
    assistantMessages: int = 0
    totalMessages: int = 0
    promptTokens: int = 0
    completionTokens: int = 0
    totalTokens: int = 0
    tokensEstimate: str
    estimatedCostUsd: float = 0
    costDisplay: str = "$0"
    percentage: int


class TopUserUsage(BaseModel):
    email: str
    tenant: str
    chats: int
    userMessages: int = 0
    assistantMessages: int = 0
    totalMessages: int = 0
    tokens: str
    costDisplay: str = "$0"
    lastActive: str


class TelemetryTenantRow(BaseModel):
    tenantId: str
    name: str
    users: int
    conversations: int
    userMessages: int
    assistantMessages: int
    totalMessages: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    tokensDisplay: str
    estimatedCostUsd: float
    costDisplay: str
    percentage: int


class TelemetryUserRow(BaseModel):
    userId: str
    email: str
    tenantId: str
    tenantName: str
    conversations: int
    userMessages: int
    assistantMessages: int
    totalMessages: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    tokensDisplay: str
    estimatedCostUsd: float
    costDisplay: str
    lastActive: str


class TelemetryTimeseriesPoint(BaseModel):
    date: str
    userMessages: int
    assistantMessages: int
    totalTokens: int
    estimatedCostUsd: float


class TelemetryOps(BaseModel):
    last24hRequests: int
    errorRatePercent: float
    avgLatencyMs: int
    groqConfigured: bool


class TelemetrySummary(BaseModel):
    periodStart: str
    periodEnd: str
    totalUserMessages: int
    totalAssistantMessages: int
    totalMessages: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    tokensDisplay: str
    estimatedCostUsd: float
    costDisplay: str
    activeUsers: int
    tenantBreakdown: list[TelemetryTenantRow]
    timeseries: list[TelemetryTimeseriesPoint] = []
    ops: TelemetryOps | None = None
    users: list[TelemetryUserRow] = []


class TelemetryPricingUpdate(BaseModel):
    cost_per_1m_input_tokens: float | None = None
    cost_per_1m_output_tokens: float | None = None


class AdminMetrics(BaseModel):
    totalUsers: int
    activeUsers: int
    totalTasks: int
    totalConversations: int
    tokensEstimate: str
    tenantBreakdown: list[TenantBreakdownItem]
    topUsers: list[TopUserUsage]


class ModelOptionOut(BaseModel):
    id: str
    provider: str
    model: str
    label: str


class PlatformConfigOut(BaseModel):
    groq_model: str
    primary_model: str
    fallback_model: str
    available_models: list[ModelOptionOut] = []
    temperature: float
    system_prompt: str
    knowledge_base: str = ""
    streaming_enabled: bool
    rate_limit_qpm: int
    groq_api_key_set: bool
    openai_api_key_set: bool = False
    system_prompt_file: str = "prompts/system_prompt.md"
    knowledge_base_file: str = "prompts/knowledge_base.md"
    cost_per_1m_input_tokens: float = 0.05
    cost_per_1m_output_tokens: float = 0.08


class PlatformConfigUpdate(BaseModel):
    groq_model: str | None = None
    primary_model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    knowledge_base: str | None = None
    streaming_enabled: bool | None = None
    rate_limit_qpm: int | None = None
    cost_per_1m_input_tokens: float | None = None
    cost_per_1m_output_tokens: float | None = None


class KbDocumentOut(BaseModel):
    id: str
    name: str
    size: str
    status: str
    uploadedAt: str


class AdminConversationSummary(BaseModel):
    id: str
    userEmail: str
    title: str
    messageCount: int
    updatedAt: datetime


class AdminTaskOut(BaseModel):
    id: str
    userId: str
    userEmail: str
    title: str
    description: str
    status: str
    priority: str
    dueDate: datetime | None = None
    createdAt: datetime | None = None
