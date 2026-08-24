-- Full baseline schema: every table, enum type, and index for the Mendyr platform
-- (users, patients, professionals, bookings/offers/visits, payments/wallet, reviews,
-- support tickets, notifications, devices, coupons). Generated once from the
-- SQLAlchemy models via `alembic upgrade base:head --sql` (offline mode, no live DB
-- needed) and committed as plain SQL from here on — see migrations/README.md.

CREATE TYPE coupon_discount_type AS ENUM ('flat', 'percentage');

CREATE TABLE coupons (
    code VARCHAR(30) NOT NULL, 
    description VARCHAR(255), 
    discount_type coupon_discount_type NOT NULL, 
    discount_value NUMERIC(10, 2) NOT NULL, 
    max_discount_amount NUMERIC(10, 2), 
    min_order_amount NUMERIC(10, 2) NOT NULL, 
    max_redemptions_total INTEGER, 
    max_redemptions_per_user SMALLINT NOT NULL, 
    valid_from TIMESTAMP WITH TIME ZONE NOT NULL, 
    valid_until TIMESTAMP WITH TIME ZONE NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_coupons PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_coupons_code ON coupons (code);

CREATE TABLE otp_verifications (
    phone_number VARCHAR(15) NOT NULL, 
    purpose VARCHAR(30) NOT NULL, 
    hashed_code VARCHAR(255) NOT NULL, 
    attempts INTEGER NOT NULL, 
    max_attempts INTEGER NOT NULL, 
    verified BOOLEAN NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_otp_verifications PRIMARY KEY (id)
);

CREATE INDEX ix_otp_phone_purpose ON otp_verifications (phone_number, purpose);

CREATE INDEX ix_otp_verifications_phone_number ON otp_verifications (phone_number);

CREATE TABLE service_categories (
    name VARCHAR(150) NOT NULL, 
    slug VARCHAR(150) NOT NULL, 
    description VARCHAR(500), 
    icon_url VARCHAR(500), 
    display_order SMALLINT NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_service_categories PRIMARY KEY (id), 
    CONSTRAINT uq_service_categories_name UNIQUE (name), 
    CONSTRAINT uq_service_categories_slug UNIQUE (slug)
);

CREATE TABLE specializations (
    name VARCHAR(150) NOT NULL, 
    description VARCHAR(500), 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_specializations PRIMARY KEY (id), 
    CONSTRAINT uq_specializations_name UNIQUE (name)
);

CREATE TYPE gender AS ENUM ('male', 'female', 'other', 'unspecified');

CREATE TYPE user_role AS ENUM ('patient', 'professional', 'admin', 'ops');

CREATE TYPE user_status AS ENUM ('active', 'suspended', 'deleted');

CREATE TABLE users (
    phone_number VARCHAR(15) NOT NULL, 
    phone_verified BOOLEAN NOT NULL, 
    email VARCHAR(255), 
    email_verified BOOLEAN NOT NULL, 
    hashed_password VARCHAR(255), 
    full_name VARCHAR(150) NOT NULL, 
    gender gender NOT NULL, 
    date_of_birth TIMESTAMP WITH TIME ZONE, 
    avatar_url VARCHAR(500), 
    role user_role NOT NULL, 
    status user_status NOT NULL, 
    referral_code VARCHAR(12) NOT NULL, 
    referred_by_id UUID, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT fk_users_referred_by_id_users FOREIGN KEY(referred_by_id) REFERENCES users (id), 
    CONSTRAINT uq_users_email UNIQUE (email), 
    CONSTRAINT uq_users_referral_code UNIQUE (referral_code)
);

CREATE UNIQUE INDEX ix_users_phone_number ON users (phone_number);

CREATE INDEX ix_users_role_status ON users (role, status);

CREATE TABLE addresses (
    user_id UUID NOT NULL, 
    label VARCHAR(30) NOT NULL, 
    line1 VARCHAR(255) NOT NULL, 
    line2 VARCHAR(255), 
    landmark VARCHAR(255), 
    city VARCHAR(100) NOT NULL, 
    state VARCHAR(100) NOT NULL, 
    pincode VARCHAR(10) NOT NULL, 
    country VARCHAR(2) NOT NULL, 
    location geography(POINT,4326) NOT NULL, 
    is_default BOOLEAN NOT NULL, 
    contact_name VARCHAR(150), 
    contact_phone VARCHAR(15), 
    instructions_for_professional VARCHAR(500), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_addresses PRIMARY KEY (id), 
    CONSTRAINT fk_addresses_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_addresses_location ON addresses USING gist (location);

CREATE INDEX ix_addresses_user_id ON addresses (user_id);

CREATE TABLE audit_logs (
    actor_id UUID, 
    action VARCHAR(100) NOT NULL, 
    entity_type VARCHAR(100) NOT NULL, 
    entity_id VARCHAR(100) NOT NULL, 
    metadata_json TEXT, 
    ip_address VARCHAR(45), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TYPE device_platform AS ENUM ('android', 'ios', 'web');

CREATE TABLE device_tokens (
    user_id UUID NOT NULL, 
    platform device_platform NOT NULL, 
    push_token VARCHAR(500) NOT NULL, 
    app_version VARCHAR(20), 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_device_tokens PRIMARY KEY (id), 
    CONSTRAINT fk_device_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_device_tokens_user_token ON device_tokens (user_id, push_token);

CREATE TYPE notification_channel AS ENUM ('push', 'sms', 'email', 'in_app');

CREATE TYPE notification_status AS ENUM ('queued', 'sent', 'failed');

CREATE TABLE notifications (
    user_id UUID NOT NULL, 
    channel notification_channel NOT NULL, 
    template_key VARCHAR(100) NOT NULL, 
    title VARCHAR(200), 
    body TEXT NOT NULL, 
    data TEXT, 
    status notification_status NOT NULL, 
    failure_reason VARCHAR(500), 
    sent_at TIMESTAMP WITH TIME ZONE, 
    read_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_notifications PRIMARY KEY (id), 
    CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE patient_profiles (
    user_id UUID NOT NULL, 
    known_conditions VARCHAR(100)[], 
    allergies VARCHAR(100)[], 
    current_medications TEXT, 
    emergency_contact_name VARCHAR(150), 
    emergency_contact_phone VARCHAR(15), 
    preferred_language VARCHAR(50), 
    notes TEXT, 
    date_of_birth TIMESTAMP WITHOUT TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_patient_profiles PRIMARY KEY (id), 
    CONSTRAINT fk_patient_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_patient_profiles_user_id UNIQUE (user_id)
);

CREATE TYPE professional_type AS ENUM ('nurse', 'physiotherapist', 'caretaker', 'lab_technician', 'doctor', 'baby_care_specialist');

CREATE TYPE verification_status AS ENUM ('pending', 'in_review', 'approved', 'rejected');

CREATE TYPE availability_status AS ENUM ('offline', 'online', 'on_visit', 'break');

CREATE TABLE professional_profiles (
    user_id UUID NOT NULL, 
    professional_type professional_type NOT NULL, 
    years_of_experience SMALLINT NOT NULL, 
    bio TEXT, 
    license_number VARCHAR(100), 
    council_registration_number VARCHAR(100), 
    languages_spoken VARCHAR(50)[], 
    verification_status verification_status NOT NULL, 
    verified_at TIMESTAMP WITH TIME ZONE, 
    rejection_reason VARCHAR(500), 
    availability_status availability_status NOT NULL, 
    current_location geography(POINT,4326), 
    location_updated_at TIMESTAMP WITH TIME ZONE, 
    base_service_radius_km NUMERIC(5, 2) NOT NULL, 
    average_rating NUMERIC(3, 2) NOT NULL, 
    total_ratings INTEGER NOT NULL, 
    total_visits_completed INTEGER NOT NULL, 
    bank_account_number VARCHAR(50), 
    bank_ifsc VARCHAR(15), 
    bank_account_holder_name VARCHAR(150), 
    upi_id VARCHAR(100), 
    is_accepting_bookings BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_professional_profiles PRIMARY KEY (id), 
    CONSTRAINT fk_professional_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_professional_profiles_user_id UNIQUE (user_id)
);

CREATE INDEX ix_professional_current_location ON professional_profiles USING gist (current_location);

CREATE INDEX ix_professional_type_status ON professional_profiles (professional_type, verification_status);

CREATE TABLE services (
    category_id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    slug VARCHAR(200) NOT NULL, 
    description TEXT, 
    required_professional_type professional_type NOT NULL, 
    duration_minutes INTEGER NOT NULL, 
    base_price NUMERIC(10, 2) NOT NULL, 
    is_recurring_eligible BOOLEAN NOT NULL, 
    requires_prescription BOOLEAN NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    display_order SMALLINT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_services PRIMARY KEY (id), 
    CONSTRAINT fk_services_category_id_service_categories FOREIGN KEY(category_id) REFERENCES service_categories (id) ON DELETE CASCADE, 
    CONSTRAINT uq_services_slug UNIQUE (slug)
);

CREATE TABLE wallets (
    user_id UUID NOT NULL, 
    balance NUMERIC(10, 2) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_wallets PRIMARY KEY (id), 
    CONSTRAINT fk_wallets_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_wallets_user_id UNIQUE (user_id)
);

CREATE TABLE care_plans (
    patient_id UUID NOT NULL, 
    service_id UUID NOT NULL, 
    address_id UUID NOT NULL, 
    total_visits SMALLINT NOT NULL, 
    visits_per_day SMALLINT NOT NULL, 
    start_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    end_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    preferred_professional_id UUID, 
    notes TEXT, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_care_plans PRIMARY KEY (id), 
    CONSTRAINT fk_care_plans_address_id_addresses FOREIGN KEY(address_id) REFERENCES addresses (id), 
    CONSTRAINT fk_care_plans_patient_id_users FOREIGN KEY(patient_id) REFERENCES users (id), 
    CONSTRAINT fk_care_plans_preferred_professional_id_professional_profiles FOREIGN KEY(preferred_professional_id) REFERENCES professional_profiles (id), 
    CONSTRAINT fk_care_plans_service_id_services FOREIGN KEY(service_id) REFERENCES services (id)
);

CREATE TYPE payout_status AS ENUM ('pending', 'processing', 'paid', 'failed');

CREATE TABLE payouts (
    professional_id UUID NOT NULL, 
    period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    total_visits INTEGER NOT NULL, 
    gross_amount NUMERIC(10, 2) NOT NULL, 
    commission_deducted NUMERIC(10, 2) NOT NULL, 
    adjustments NUMERIC(10, 2) NOT NULL, 
    net_amount NUMERIC(10, 2) NOT NULL, 
    status payout_status NOT NULL, 
    provider_reference_id VARCHAR(100), 
    failure_reason VARCHAR(500), 
    paid_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_payouts PRIMARY KEY (id), 
    CONSTRAINT fk_payouts_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id)
);

CREATE INDEX ix_payouts_professional_id ON payouts (professional_id);

CREATE TABLE professional_availability_slots (
    professional_id UUID NOT NULL, 
    day_of_week SMALLINT NOT NULL, 
    start_time TIME WITHOUT TIME ZONE NOT NULL, 
    end_time TIME WITHOUT TIME ZONE NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_professional_availability_slots PRIMARY KEY (id), 
    CONSTRAINT fk_professional_availability_slots_professional_id_prof_1a7e FOREIGN KEY(professional_id) REFERENCES professional_profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_availability_professional_day ON professional_availability_slots (professional_id, day_of_week);

CREATE TYPE document_type AS ENUM ('government_id', 'nursing_council_certificate', 'degree_certificate', 'police_verification', 'profile_photo', 'address_proof');

CREATE TABLE professional_documents (
    professional_id UUID NOT NULL, 
    document_type document_type NOT NULL, 
    file_url VARCHAR(500) NOT NULL, 
    verification_status verification_status NOT NULL, 
    reviewed_by_id UUID, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    rejection_reason VARCHAR(500), 
    expires_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_professional_documents PRIMARY KEY (id), 
    CONSTRAINT fk_professional_documents_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id) ON DELETE CASCADE, 
    CONSTRAINT fk_professional_documents_reviewed_by_id_users FOREIGN KEY(reviewed_by_id) REFERENCES users (id)
);

CREATE TABLE professional_services (
    professional_id UUID NOT NULL, 
    service_id UUID NOT NULL, 
    price_override NUMERIC(10, 2), 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_professional_services PRIMARY KEY (id), 
    CONSTRAINT fk_professional_services_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id) ON DELETE CASCADE, 
    CONSTRAINT fk_professional_services_service_id_services FOREIGN KEY(service_id) REFERENCES services (id) ON DELETE CASCADE, 
    CONSTRAINT uq_professional_service UNIQUE (professional_id, service_id)
);

CREATE TABLE professional_specializations (
    professional_id UUID NOT NULL, 
    specialization_id UUID NOT NULL, 
    years_of_experience SMALLINT NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_professional_specializations PRIMARY KEY (id), 
    CONSTRAINT fk_professional_specializations_professional_id_profess_2d30 FOREIGN KEY(professional_id) REFERENCES professional_profiles (id) ON DELETE CASCADE, 
    CONSTRAINT fk_professional_specializations_specialization_id_speci_dadb FOREIGN KEY(specialization_id) REFERENCES specializations (id) ON DELETE CASCADE, 
    CONSTRAINT uq_professional_specialization UNIQUE (professional_id, specialization_id)
);

CREATE TYPE booking_type AS ENUM ('one_time', 'care_plan');

CREATE TYPE booking_status AS ENUM ('created', 'searching', 'assigned', 'confirmed', 'en_route', 'in_progress', 'completed', 'cancelled', 'no_show', 'failed');

CREATE TABLE bookings (
    booking_code VARCHAR(20) NOT NULL, 
    patient_id UUID NOT NULL, 
    professional_id UUID, 
    service_id UUID NOT NULL, 
    address_id UUID NOT NULL, 
    care_plan_id UUID, 
    booking_type booking_type NOT NULL, 
    status booking_status NOT NULL, 
    required_professional_type professional_type NOT NULL, 
    scheduled_start_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    scheduled_end_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    service_name_snapshot VARCHAR(200) NOT NULL, 
    address_snapshot TEXT NOT NULL, 
    service_location geography(POINT,4326) NOT NULL, 
    base_price NUMERIC(10, 2) NOT NULL, 
    discount_amount NUMERIC(10, 2) NOT NULL, 
    platform_fee NUMERIC(10, 2) NOT NULL, 
    tax_amount NUMERIC(10, 2) NOT NULL, 
    total_amount NUMERIC(10, 2) NOT NULL, 
    professional_payout_amount NUMERIC(10, 2) NOT NULL, 
    commission_pct NUMERIC(5, 2) NOT NULL, 
    coupon_id UUID, 
    patient_notes TEXT, 
    cancellation_reason VARCHAR(500), 
    cancelled_by_id UUID, 
    cancelled_at TIMESTAMP WITH TIME ZONE, 
    cancellation_fee_amount NUMERIC(10, 2) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_bookings PRIMARY KEY (id), 
    CONSTRAINT fk_bookings_address_id_addresses FOREIGN KEY(address_id) REFERENCES addresses (id), 
    CONSTRAINT fk_bookings_cancelled_by_id_users FOREIGN KEY(cancelled_by_id) REFERENCES users (id), 
    CONSTRAINT fk_bookings_care_plan_id_care_plans FOREIGN KEY(care_plan_id) REFERENCES care_plans (id), 
    CONSTRAINT fk_bookings_coupon_id_coupons FOREIGN KEY(coupon_id) REFERENCES coupons (id), 
    CONSTRAINT fk_bookings_patient_id_users FOREIGN KEY(patient_id) REFERENCES users (id), 
    CONSTRAINT fk_bookings_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id), 
    CONSTRAINT fk_bookings_service_id_services FOREIGN KEY(service_id) REFERENCES services (id), 
    CONSTRAINT uq_bookings_booking_code UNIQUE (booking_code)
);

CREATE INDEX ix_bookings_patient_status ON bookings (patient_id, status);

CREATE INDEX ix_bookings_professional_status ON bookings (professional_id, status);

CREATE INDEX ix_bookings_scheduled_start ON bookings (scheduled_start_at);

CREATE TYPE offer_status AS ENUM ('pending', 'accepted', 'rejected', 'expired', 'cancelled');

CREATE TABLE booking_offers (
    booking_id UUID NOT NULL, 
    professional_id UUID NOT NULL, 
    round_number SMALLINT NOT NULL, 
    distance_meters INTEGER NOT NULL, 
    status offer_status NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    responded_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_booking_offers PRIMARY KEY (id), 
    CONSTRAINT fk_booking_offers_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE, 
    CONSTRAINT fk_booking_offers_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id)
);

CREATE INDEX ix_offers_booking_round ON booking_offers (booking_id, round_number);

CREATE INDEX ix_offers_professional_status ON booking_offers (professional_id, status);

CREATE TABLE booking_status_history (
    booking_id UUID NOT NULL, 
    from_status booking_status, 
    to_status booking_status NOT NULL, 
    changed_by_id UUID, 
    reason VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_booking_status_history PRIMARY KEY (id), 
    CONSTRAINT fk_booking_status_history_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE, 
    CONSTRAINT fk_booking_status_history_changed_by_id_users FOREIGN KEY(changed_by_id) REFERENCES users (id)
);

CREATE TABLE booking_visits (
    booking_id UUID NOT NULL, 
    en_route_at TIMESTAMP WITH TIME ZONE, 
    checked_in_at TIMESTAMP WITH TIME ZONE, 
    checked_in_location geography(POINT,4326), 
    checked_in_distance_meters INTEGER, 
    checked_out_at TIMESTAMP WITH TIME ZONE, 
    checked_out_location geography(POINT,4326), 
    visit_summary_notes TEXT, 
    vitals_recorded TEXT, 
    proof_of_visit_photo_url VARCHAR(500), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_booking_visits PRIMARY KEY (id), 
    CONSTRAINT fk_booking_visits_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE, 
    CONSTRAINT uq_booking_visits_booking_id UNIQUE (booking_id)
);

CREATE TABLE coupon_redemptions (
    coupon_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    booking_id UUID NOT NULL, 
    discount_applied NUMERIC(10, 2) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_coupon_redemptions PRIMARY KEY (id), 
    CONSTRAINT fk_coupon_redemptions_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id), 
    CONSTRAINT fk_coupon_redemptions_coupon_id_coupons FOREIGN KEY(coupon_id) REFERENCES coupons (id) ON DELETE CASCADE, 
    CONSTRAINT fk_coupon_redemptions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
    CONSTRAINT uq_coupon_booking UNIQUE (coupon_id, booking_id)
);

CREATE TYPE payment_method AS ENUM ('upi', 'card', 'netbanking', 'wallet', 'cash');

CREATE TYPE payment_status AS ENUM ('pending', 'authorized', 'captured', 'failed', 'refunded', 'partially_refunded');

CREATE TABLE payments (
    booking_id UUID NOT NULL, 
    patient_id UUID NOT NULL, 
    provider VARCHAR(30) NOT NULL, 
    provider_order_id VARCHAR(100), 
    provider_payment_id VARCHAR(100), 
    provider_signature VARCHAR(255), 
    method payment_method, 
    status payment_status NOT NULL, 
    amount NUMERIC(10, 2) NOT NULL, 
    amount_refunded NUMERIC(10, 2) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    failure_reason VARCHAR(500), 
    captured_at TIMESTAMP WITH TIME ZONE, 
    refunded_at TIMESTAMP WITH TIME ZONE, 
    raw_webhook_payload TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_payments PRIMARY KEY (id), 
    CONSTRAINT fk_payments_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE, 
    CONSTRAINT fk_payments_patient_id_users FOREIGN KEY(patient_id) REFERENCES users (id)
);

CREATE INDEX ix_payments_booking_id ON payments (booking_id);

CREATE INDEX ix_payments_provider_order_id ON payments (provider_order_id);

CREATE INDEX ix_payments_provider_payment_id ON payments (provider_payment_id);

CREATE TABLE reviews (
    booking_id UUID NOT NULL, 
    reviewer_id UUID NOT NULL, 
    reviewee_id UUID NOT NULL, 
    rating SMALLINT NOT NULL, 
    comment VARCHAR(1000), 
    tags VARCHAR(50)[], 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_reviews PRIMARY KEY (id), 
    CONSTRAINT ck_reviews_rating_range CHECK (rating >= 1 AND rating <= 5), 
    CONSTRAINT fk_reviews_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE, 
    CONSTRAINT fk_reviews_reviewee_id_users FOREIGN KEY(reviewee_id) REFERENCES users (id), 
    CONSTRAINT fk_reviews_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id), 
    CONSTRAINT uq_review_booking_reviewer UNIQUE (booking_id, reviewer_id)
);

CREATE TYPE support_ticket_priority AS ENUM ('low', 'medium', 'high', 'urgent');

CREATE TYPE support_ticket_status AS ENUM ('open', 'in_progress', 'resolved', 'closed');

CREATE TABLE support_tickets (
    raised_by_id UUID NOT NULL, 
    booking_id UUID, 
    assigned_to_id UUID, 
    subject VARCHAR(255) NOT NULL, 
    category VARCHAR(50) NOT NULL, 
    priority support_ticket_priority NOT NULL, 
    status support_ticket_status NOT NULL, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_support_tickets PRIMARY KEY (id), 
    CONSTRAINT fk_support_tickets_assigned_to_id_users FOREIGN KEY(assigned_to_id) REFERENCES users (id), 
    CONSTRAINT fk_support_tickets_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id), 
    CONSTRAINT fk_support_tickets_raised_by_id_users FOREIGN KEY(raised_by_id) REFERENCES users (id)
);

CREATE TYPE visit_event AS ENUM ('en_route', 'checked_in', 'checked_out');

CREATE TABLE visit_tracking_pings (
    booking_id UUID NOT NULL, 
    event visit_event NOT NULL, 
    location geography(POINT,4326) NOT NULL, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_visit_tracking_pings PRIMARY KEY (id), 
    CONSTRAINT fk_visit_tracking_pings_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id) ON DELETE CASCADE
);

CREATE INDEX ix_tracking_booking_time ON visit_tracking_pings (booking_id, recorded_at);

CREATE TYPE wallet_txn_type AS ENUM ('credit', 'debit');

CREATE TYPE wallet_txn_reason AS ENUM ('referral_bonus', 'cancellation_refund', 'booking_payment', 'payout', 'adjustment', 'promotion');

CREATE TABLE wallet_transactions (
    wallet_id UUID NOT NULL, 
    txn_type wallet_txn_type NOT NULL, 
    reason wallet_txn_reason NOT NULL, 
    amount NUMERIC(10, 2) NOT NULL, 
    balance_after NUMERIC(10, 2) NOT NULL, 
    reference_booking_id UUID, 
    description VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_wallet_transactions PRIMARY KEY (id), 
    CONSTRAINT fk_wallet_transactions_reference_booking_id_bookings FOREIGN KEY(reference_booking_id) REFERENCES bookings (id), 
    CONSTRAINT fk_wallet_transactions_wallet_id_wallets FOREIGN KEY(wallet_id) REFERENCES wallets (id) ON DELETE CASCADE
);

CREATE TABLE support_ticket_messages (
    ticket_id UUID NOT NULL, 
    sender_id UUID NOT NULL, 
    message TEXT NOT NULL, 
    attachment_url VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_support_ticket_messages PRIMARY KEY (id), 
    CONSTRAINT fk_support_ticket_messages_sender_id_users FOREIGN KEY(sender_id) REFERENCES users (id), 
    CONSTRAINT fk_support_ticket_messages_ticket_id_support_tickets FOREIGN KEY(ticket_id) REFERENCES support_tickets (id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('fd5a5a27db20') RETURNING alembic_version.version_num;
