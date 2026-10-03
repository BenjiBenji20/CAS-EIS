from enum import Enum

# Developer defined roles, module, resources, and actions
# Production system permissions or attributes are defined by a dedicated endpoints
# Which then be stored in database.

# THESE ARE JUST INITIAL AND GENERIC ATTRIBUTES

class RoleName(str, Enum):
    """Core System Roles (Generic & Reusable)."""
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    STAFF_USER = "STAFF_USER"
    PUBLIC_USER = "PUBLIC_USER"


class ModuleName(str, Enum):
    """Functional system modules (matching src/modules directory names)."""
    AUTHENTICATION = "AUTHENTICATION"
    PROFILE = "PROFILE"
    SYSTEM = "SYSTEM"


class ResourceName(str, Enum):
    """Target resources / domain entities / endpoints."""
    USER = "USER"
    REGISTRATION = "REGISTRATION"
    ROLE = "ROLE"
    PERMISSION = "PERMISSION"


class ActionName(str, Enum):
    """Actions performable on resources."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    GRANT = "GRANT"


class SystemPermission(str, Enum):
    """
    Standard formatted permission strings: MODULE:RESOURCE:ACTION
    Format: ALL UPPERCASE. Used for type-safe code checks and DB seeding.
    """
    # Authentication & User Management
    AUTHENTICATION_USER_CREATE = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.USER.value}:{ActionName.CREATE.value}"
    AUTHENTICATION_USER_READ = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.USER.value}:{ActionName.READ.value}"
    AUTHENTICATION_USER_UPDATE = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.USER.value}:{ActionName.UPDATE.value}"
    AUTHENTICATION_USER_DELETE = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.USER.value}:{ActionName.DELETE.value}"

    # Registration & Role Approval Endpoints
    AUTHENTICATION_REGISTRATION_ACCEPT = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.REGISTRATION.value}:{ActionName.ACCEPT.value}"
    AUTHENTICATION_REGISTRATION_REJECT = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.REGISTRATION.value}:{ActionName.REJECT.value}"
    AUTHENTICATION_ROLE_GRANT = f"{ModuleName.AUTHENTICATION.value}:{ResourceName.ROLE.value}:{ActionName.GRANT.value}"

    # Profile Module
    PROFILE_USER_READ = f"{ModuleName.PROFILE.value}:{ResourceName.USER.value}:{ActionName.READ.value}"
    PROFILE_USER_UPDATE = f"{ModuleName.PROFILE.value}:{ResourceName.USER.value}:{ActionName.UPDATE.value}"
