"""Imports all mappings so Alembic sees the complete modular-monolith metadata."""

from app.audit.models import AuditEvent
from app.auth.models import AuthenticationAttempt, RefreshToken, TenantMembership, User
from app.content.models import (
    Banner,
    ContactRequest,
    GalleryAlbum,
    GalleryItem,
    Honor,
    HonorCategory,
    Post,
    PostMediaReference,
    SampleExam,
    SchoolDirectoryEntry,
    StaffMember,
)
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.media.models import MediaAsset
from app.payments.models import PaymentTransaction
from app.registrations.models import (
    OTPChallenge,
    Registration,
    RegistrationContact,
    RegistrationFormDefinition,
)
from app.site_builds.models import SiteBuildRequest, TenantSiteBuildConfig, TenantSiteState
from app.tenancy.models import (
    Tenant,
    TenantAddress,
    TenantDomain,
    TenantFeature,
    TenantPhone,
    TenantProfile,
    TenantSocialLink,
)

__all__ = [
    "AuditEvent",
    "AuthenticationAttempt",
    "Banner",
    "ContactRequest",
    "ExamOffering",
    "ExamPricingPlan",
    "GalleryAlbum",
    "GalleryItem",
    "Honor",
    "HonorCategory",
    "MediaAsset",
    "OTPChallenge",
    "PaymentTransaction",
    "Post",
    "PostMediaReference",
    "PricingPlan",
    "RefreshToken",
    "Registration",
    "RegistrationContact",
    "RegistrationFormDefinition",
    "SampleExam",
    "SchoolDirectoryEntry",
    "SiteBuildRequest",
    "StaffMember",
    "Tenant",
    "TenantAddress",
    "TenantDomain",
    "TenantFeature",
    "TenantMembership",
    "TenantPhone",
    "TenantProfile",
    "TenantSiteBuildConfig",
    "TenantSiteState",
    "TenantSocialLink",
    "User",
]
