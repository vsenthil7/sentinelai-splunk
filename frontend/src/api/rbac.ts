import type { Role } from "../types";

export type Permission =
  | "search:run"
  | "detection:run"
  | "investigation:read"
  | "investigation:run"
  | "action:approve"
  | "case:write"
  | "audit:read"
  | "admin:*";

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  viewer: ["investigation:read"],
  analyst: [
    "investigation:read",
    "search:run",
    "detection:run",
    "investigation:run",
    "case:write",
  ],
  responder: [
    "investigation:read",
    "search:run",
    "detection:run",
    "investigation:run",
    "case:write",
    "action:approve",
  ],
  admin: [
    "investigation:read",
    "search:run",
    "detection:run",
    "investigation:run",
    "case:write",
    "action:approve",
    "audit:read",
    "admin:*",
  ],
};

export function can(role: Role | null, permission: Permission): boolean {
  if (!role) return false;
  const perms = ROLE_PERMISSIONS[role] ?? [];
  return perms.includes("admin:*") || perms.includes(permission);
}
