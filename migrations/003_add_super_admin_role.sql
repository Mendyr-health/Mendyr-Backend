-- The Next.js admin console has a SUPER_ADMIN role (platform governance: manage admins,
-- roles, audit logs) one level above ADMIN, which the original user_role enum didn't have.
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin';
