-- Schema needed to back the frontend's screens that had no matching backend data yet:
-- the public waitlist and contact-us forms, patient<->nurse messaging, the Super Admin
-- platform settings singleton, and registration-time profile fields (qualifications,
-- certifications, preferred contact method, free-text registration address, experience
-- description, emergency contact relationship).

CREATE TYPE preferred_contact_method AS ENUM ('email', 'phone', 'whatsapp');

ALTER TABLE professional_profiles ADD COLUMN experience_description TEXT;

ALTER TABLE professional_profiles ADD COLUMN qualifications TEXT;

ALTER TABLE professional_profiles ADD COLUMN certifications TEXT;

ALTER TABLE professional_profiles ADD COLUMN preferred_contact preferred_contact_method DEFAULT 'email' NOT NULL;

ALTER TABLE professional_profiles ADD COLUMN address_line TEXT;

ALTER TABLE professional_profiles ADD COLUMN city VARCHAR(100);

ALTER TABLE professional_profiles ADD COLUMN state VARCHAR(100);

ALTER TABLE patient_profiles ADD COLUMN emergency_contact_relationship VARCHAR(100);

ALTER TABLE patient_profiles ADD COLUMN address_line TEXT;

ALTER TABLE patient_profiles ADD COLUMN city VARCHAR(100);

ALTER TABLE patient_profiles ADD COLUMN state VARCHAR(100);

CREATE TABLE waitlist_entries (
    email VARCHAR(255) NOT NULL, 
    name VARCHAR(150), 
    phone VARCHAR(15), 
    source VARCHAR(50), 
    notified BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_waitlist_entries PRIMARY KEY (id), 
    CONSTRAINT uq_waitlist_entries_email UNIQUE (email)
);

CREATE INDEX ix_waitlist_entries_email ON waitlist_entries (email);

CREATE TYPE contact_inquiry_status AS ENUM ('new', 'in_progress', 'resolved');

CREATE TABLE contact_inquiries (
    name VARCHAR(100) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    phone VARCHAR(15), 
    subject VARCHAR(200) NOT NULL, 
    message TEXT NOT NULL, 
    status contact_inquiry_status NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_contact_inquiries PRIMARY KEY (id)
);

CREATE INDEX ix_contact_inquiries_email ON contact_inquiries (email);

CREATE TABLE message_threads (
    patient_id UUID NOT NULL, 
    professional_id UUID NOT NULL, 
    booking_id UUID, 
    last_message_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_message_threads PRIMARY KEY (id), 
    CONSTRAINT fk_message_threads_booking_id_bookings FOREIGN KEY(booking_id) REFERENCES bookings (id), 
    CONSTRAINT fk_message_threads_patient_id_users FOREIGN KEY(patient_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT fk_message_threads_professional_id_professional_profiles FOREIGN KEY(professional_id) REFERENCES professional_profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_message_threads_patient ON message_threads (patient_id);

CREATE INDEX ix_message_threads_professional ON message_threads (professional_id);

CREATE TABLE messages (
    thread_id UUID NOT NULL, 
    sender_id UUID NOT NULL, 
    body TEXT NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    is_read BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_messages PRIMARY KEY (id), 
    CONSTRAINT fk_messages_sender_id_users FOREIGN KEY(sender_id) REFERENCES users (id), 
    CONSTRAINT fk_messages_thread_id_message_threads FOREIGN KEY(thread_id) REFERENCES message_threads (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_thread_created ON messages (thread_id, created_at);

CREATE TABLE platform_settings (
    id SERIAL NOT NULL, 
    platform_name VARCHAR(100) NOT NULL, 
    support_email VARCHAR(255), 
    support_phone VARCHAR(15), 
    maintenance_mode BOOLEAN NOT NULL, 
    new_registrations_enabled BOOLEAN NOT NULL, 
    platform_commission_pct NUMERIC(5, 2) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_platform_settings PRIMARY KEY (id)
);

INSERT INTO platform_settings (id, platform_name, maintenance_mode, new_registrations_enabled, platform_commission_pct) VALUES (1, 'Mendyr', false, true, 20);
