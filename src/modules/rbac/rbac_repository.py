from typing import Dict, List, Optional, Sequence
from uuid import UUID

from base.repository import BaseRepository
from db.db_session import get_async_db
from exceptions.app_exception import InternalServerException
from fastapi import Depends
from loguru import logger
from modules.authentication.auth_model import Permission, Role, RolePermission, UserRole
from shares.enums import (
    ACTION_DESCRIPTIONS,
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ActionName,
    RoleName,
    SystemPermission,
)
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class RBACRepository(BaseRepository[Role]):
    """Repository for database operations related to Roles and Permissions."""

    def __init__(
        self, 
        db: AsyncSession = Depends(get_async_db)
    ):
        super().__init__(db, Role)


    async def get_user_roles_and_permissions(
        self, user_id: UUID
    ) -> Dict[str, any]:
        """
        Fetches all assigned role names and permission codes for a given user UUID.
        
        Flow:
        1. Fetch role names from auth.user_roles joined with auth.roles.
        2. Fetch permission codes from auth.user_roles -> auth.role_permissions -> auth.permissions.
        3. Returns structured dict: {"user_id": str(user_id), "roles": [...], "permissions": [...]}
        """
        try:
            # Fetch assigned role names
            role_stmt = (
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            )
            role_res = await self.db.execute(role_stmt)

            # Fetch assigned permission codes
            perm_stmt = (
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user_id)
            )
            perm_res = await self.db.execute(perm_stmt)

            valid_role_names = {r.value for r in RoleName}
            valid_perm_codes = {p.value for p in SystemPermission}

            # Filter against active enums in enums.py (source of truth)
            roles: List[str] = [r[0] for r in role_res.fetchall() if r[0] in valid_role_names]
            permissions: List[str] = list(set([p[0] for p in perm_res.fetchall() if p[0] in valid_perm_codes]))


            return {
                "user_id": str(user_id),
                "roles": roles,
                "permissions": permissions
            }
        except Exception as e:
            logger.error(f"Failed to query roles and permissions for user {user_id}: {e}")
            raise InternalServerException(
                message="Error querying user roles and permissions.",
                error_code="USER_ROLE_PERMISSION_FAILED"
            )


    async def get_all_roles(self) -> List[Role]:
        """Fetches active roles defined in enums.py with active permissions loaded."""
        try:
            valid_role_names = {r.value for r in RoleName}
            valid_perm_codes = {p.value for p in SystemPermission}

            stmt = (
                select(Role)
                .options(selectinload(Role.permissions))
                .where(Role.name.in_(valid_role_names))
                .order_by(Role.name.asc())
            )
            res = await self.db.execute(stmt)
            roles = list(res.scalars().all())

            # Filter permissions inside each role to active SystemPermission enums
            for r in roles:
                r.permissions = [p for p in r.permissions if p.code in valid_perm_codes]

            return roles
        except Exception as e:
            logger.error(f"Failed to fetch roles: {e}")
            raise InternalServerException(
                message="Failed to retrieve system roles.",
                error_code="ROLES_QUERY_FAILED"
            )


    async def get_role_by_identifier(self, identifier: str) -> Optional[Role]:
        """Fetch active role by either UUID string or role name with active permissions loaded."""
        valid_role_names = {r.value for r in RoleName}
        valid_perm_codes = {p.value for p in SystemPermission}

        stmt = select(Role).options(selectinload(Role.permissions))
        try:
            parsed_uuid = UUID(identifier)
            stmt = stmt.where(Role.id == parsed_uuid)
        except (ValueError, AttributeError):
            stmt = stmt.where(Role.name == identifier)

        res = await self.db.execute(stmt)
        role = res.scalar_one_or_none()
        if role and role.name in valid_role_names:
            role.permissions = [p for p in role.permissions if p.code in valid_perm_codes]
            return role
        return None


    async def get_role_by_id(self, role_id: UUID) -> Optional[Role]:
        """Fetch a single active role by its UUID with active permissions eagerly loaded."""
        return await self.get_role_by_identifier(str(role_id))


    async def resolve_roles(self, identifiers: Sequence[str]) -> List[Role]:
        """Batch resolves role names or UUID strings to active Role models."""
        if not identifiers:
            return []
        valid_role_names = {r.value for r in RoleName}

        uuid_list = []
        name_list = []
        for item in identifiers:
            try:
                uuid_list.append(UUID(str(item)))
            except (ValueError, AttributeError):
                name_list.append(str(item))

        conditions = []
        if uuid_list:
            conditions.append(Role.id.in_(uuid_list))
        if name_list:
            conditions.append(Role.name.in_(name_list))

        if not conditions:
            return []

        stmt = (
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.name.in_(valid_role_names))
            .where(or_(*conditions))
        )
        res = await self.db.execute(stmt)
        roles = list(res.scalars().all())
        valid_perm_codes = {p.value for p in SystemPermission}
        for r in roles:
            r.permissions = [p for p in r.permissions if p.code in valid_perm_codes]
        return roles


    async def resolve_permissions(self, identifiers: Sequence[str]) -> List[Permission]:
        """Batch resolves permission codes or UUID strings to active Permission models."""
        if not identifiers:
            return []
        valid_perm_codes = {p.value for p in SystemPermission}

        uuid_list = []
        code_list = []
        for item in identifiers:
            try:
                uuid_list.append(UUID(str(item)))
            except (ValueError, AttributeError):
                code_list.append(str(item))

        conditions = []
        if uuid_list:
            conditions.append(Permission.id.in_(uuid_list))
        if code_list:
            conditions.append(Permission.code.in_(code_list))

        if not conditions:
            return []

        stmt = (
            select(Permission)
            .where(Permission.code.in_(valid_perm_codes))
            .where(or_(*conditions))
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


    async def get_all_permissions(self) -> List[Permission]:
        """Fetch active permissions defined in enums.py."""
        valid_perm_codes = {p.value for p in SystemPermission}
        stmt = (
            select(Permission)
            .where(Permission.code.in_(valid_perm_codes))
            .order_by(Permission.module.asc(), Permission.code.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


    async def get_roles_by_ids(self, role_ids: List[UUID]) -> Sequence[Role]:
        """Fetch roles matching the given list of UUIDs using BaseRepository."""
        return await self.get_by_ids(role_ids)


    async def get_permissions_by_ids(self, permission_ids: List[UUID]) -> List[Permission]:
        """Fetch permissions matching the given list of UUIDs."""
        stmt = select(Permission).where(Permission.id.in_(permission_ids))
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


    async def assign_roles_to_user(self, user_id: UUID, role_ids: List[UUID]) -> List[str]:
        """
        Replaces all assigned roles for a user with the provided role_ids.
        Returns list of newly assigned role names.
        """
        try:
            # Delete current assignments
            del_stmt = delete(UserRole).where(UserRole.user_id == user_id)
            await self.db.execute(del_stmt)

            # Insert new assignments
            for r_id in role_ids:
                self.db.add(UserRole(user_id=user_id, role_id=r_id))

            await self.db.flush()

            # Query assigned role names
            role_stmt = select(Role.name).where(Role.id.in_(role_ids))
            role_res = await self.db.execute(role_stmt)
            return [r[0] for r in role_res.fetchall()]
        except Exception as e:
            logger.error(f"Failed to assign roles to user {user_id}: {e}")
            raise InternalServerException(
                message="Failed to update user roles.",
                error_code="USER_ROLE_ASSIGNMENT_FAILED"
            )


    async def assign_permissions_to_role(
        self, role_id: UUID, permission_ids: List[UUID]
    ) -> List[str]:
        """
        Replaces all assigned permissions for a role with the provided permission_ids.
        Returns list of newly assigned permission codes.
        """
        try:
            # Delete current assignments
            del_stmt = delete(RolePermission).where(RolePermission.role_id == role_id)
            await self.db.execute(del_stmt)

            # Insert new assignments
            for p_id in permission_ids:
                self.db.add(RolePermission(role_id=role_id, permission_id=p_id))

            await self.db.flush()

            # Query assigned permission codes
            perm_stmt = select(Permission.code).where(Permission.id.in_(permission_ids))
            perm_res = await self.db.execute(perm_stmt)
            return [p[0] for p in perm_res.fetchall()]
        except Exception as e:
            logger.error(f"Failed to assign permissions to role {role_id}: {e}")
            raise InternalServerException(
                message="Failed to update role permissions.",
                error_code="ROLE_PERMISSION_ASSIGNMENT_FAILED"
            )


    async def get_user_ids_by_role(self, role_id: UUID) -> List[UUID]:
        """Retrieves all user IDs who are assigned a given role."""
        stmt = select(UserRole.user_id).where(UserRole.role_id == role_id)
        res = await self.db.execute(stmt)
        return [r[0] for r in res.fetchall()]


    async def sync_enums_to_db(self) -> dict:
        """
        Idempotent synchronization and lifespan pruning helper.
        1. Ensures all roles and permissions defined in `enums.py` exist with rich descriptions.
        2. Links default bulk permissions according to `ROLE_DEFAULT_PERMISSIONS`.
        3. Lifespan Pruning (Non-destructive): Detaches obsolete associations from
           auth.role_permissions and auth.user_roles without deleting audit table rows.
        """
        roles_synced = 0
        perms_synced = 0
        valid_role_names = {r.value for r in RoleName}
        valid_perm_codes = {p.value for p in SystemPermission}

        # 1. Sync Roles
        role_map: dict[str, Role] = {}
        for r_enum in RoleName:
            stmt = select(Role).options(
                selectinload(Role.permissions)
            ).where(Role.name == r_enum.value)

            res = await self.db.execute(stmt)
            role = res.scalar_one_or_none()
            desc = ROLE_DESCRIPTIONS.get(r_enum, f"System role for {r_enum.value}")

            if not role:
                role = Role(
                    name=r_enum.value,
                    description=desc,
                    is_system_role=True,
                )
                self.db.add(role)
                await self.db.flush()
                roles_synced += 1
            else:
                if role.description != desc:
                    role.description = desc
                    self.db.add(role)
            role_map[r_enum.value] = role

        # 2. Sync Permissions
        perm_map: dict[str, Permission] = {}
        for p_enum in SystemPermission:
            code_str = p_enum.value
            parts = code_str.split(":")
            module_name = parts[0]
            res_name = parts[1] if len(parts) > 1 else ""
            act_name = parts[2] if len(parts) > 2 else ""

            display_name = f"{res_name} {act_name}".strip()
            desc = ""
            try:
                desc = ACTION_DESCRIPTIONS.get(ActionName(act_name), f"System permission for {display_name}")
            except ValueError:
                desc = f"System permission for {display_name}"

            stmt = select(Permission).where(Permission.code == code_str)
            res = await self.db.execute(stmt)
            perm = res.scalar_one_or_none()
            if not perm:
                perm = Permission(
                    code=code_str,
                    module=module_name,
                    name=display_name,
                    description=desc,
                )
                self.db.add(perm)
                await self.db.flush()
                perms_synced += 1
            else:
                if perm.description != desc or perm.name != display_name or perm.module != module_name:
                    perm.description = desc
                    perm.name = display_name
                    perm.module = module_name
                    self.db.add(perm)
            perm_map[code_str] = perm

        # 3. Sync Default Role Permissions
        links_added = 0
        for r_enum, perm_set in ROLE_DEFAULT_PERMISSIONS.items():
            role = role_map.get(r_enum.value)
            if not role:
                continue
            existing_perm_ids = {p.id for p in role.permissions}
            for p_enum in perm_set:
                perm = perm_map.get(p_enum.value)
                if perm and perm.id not in existing_perm_ids:
                    self.db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                    links_added += 1

        # 4. Lifespan Pruning: Detach obsolete permissions & roles from junction tables
        # Detach obsolete permissions from role_permissions
        obsolete_perm_subq = select(Permission.id).where(Permission.code.notin_(valid_perm_codes))
        prune_perm_stmt = delete(RolePermission).where(RolePermission.permission_id.in_(obsolete_perm_subq))
        prune_perm_res = await self.db.execute(prune_perm_stmt)
        pruned_perm_links = prune_perm_res.rowcount or 0

        # Detach obsolete roles from user_roles and role_permissions
        obsolete_role_subq = select(Role.id).where(Role.name.notin_(valid_role_names))
        prune_user_roles_stmt = delete(UserRole).where(UserRole.role_id.in_(obsolete_role_subq))
        prune_user_roles_res = await self.db.execute(prune_user_roles_stmt)
        pruned_user_role_links = prune_user_roles_res.rowcount or 0

        await self.db.commit()
        logger.info(
            f"RBAC enum sync & lifespan pruning completed: {roles_synced} roles, {perms_synced} perms synced, "
            f"{links_added} links added, {pruned_perm_links} obsolete perm links pruned, "
            f"{pruned_user_role_links} obsolete user role links pruned."
        )
        return {
            "roles_synced": roles_synced,
            "permissions_synced": perms_synced,
            "links_added": links_added,
            "pruned_perm_links": pruned_perm_links,
            "pruned_user_role_links": pruned_user_role_links,
        }
