-- Agent configs (global / company_id NULL) — generated from local executors/configs/*.json
-- Run in the Supabase SQL editor on a clean agent_configs table.

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'escalation_router',
    '{
    "agent_name": "escalation_router",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "low",
    "approval": "none",
    "steps": [
        {
            "name": "extract_task_context",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "department",
                    "priority_score",
                    "requester_name",
                    "task_title"
                ]
            }
        },
        {
            "name": "select_reviewer",
            "type": "processor",
            "class": "DBFetcher",
            "config": {
                "table": "routing_table",
                "match_on": [
                    "department",
                    "priority_label"
                ]
            }
        },
        {
            "name": "draft_escalation_email",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_escalation_brief",
                "tone": "urgent"
            }
        },
        {
            "name": "send_brief",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "execution.steps.select_reviewer.data.reviewer_email",
                "log_audit": true
            }
        },
        {
            "name": "notify_requester",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_name",
                "log_audit": true
            }
        }
    ],
    "on_failure": "log_and_alert",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'document_summarizer',
    '{
    "agent_name": "document_summarizer",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "low",
    "approval": "none",
    "steps": [
        {
            "name": "extract_file",
            "type": "extractor",
            "class": "FileExtractor",
            "config": {
                "accepted_formats": [
                    "pdf",
                    "docx",
                    "txt"
                ],
                "chunk_size": 1500,
                "overlap_pct": 0.2
            }
        },
        {
            "name": "summarise_chunks",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "summarise_chunk",
                "temperature": 0.2,
                "strategy": "map_reduce"
            }
        },
        {
            "name": "extract_entities",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "extract_entities",
                "fields": [
                    "people",
                    "dates",
                    "amounts",
                    "departments"
                ]
            }
        },
        {
            "name": "draft_summary_email",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_summary_ready",
                "tone": "professional"
            }
        },
        {
            "name": "send_summary_email",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_name",
                "log_audit": true
            }
        },
        {
            "name": "store_summary",
            "type": "dispatcher",
            "class": "FileDispatcher",
            "config": {
                "output_dir": "output/summaries",
                "format": "json"
            }
        }
    ],
    "on_failure": "return_partial",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'report_generator',
    '{
    "agent_name": "report_generator",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "medium",
    "approval": "single_confirm",
    "steps": [
        {
            "name": "extract_report_params",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "report_type",
                    "date_range",
                    "department",
                    "format"
                ]
            }
        },
        {
            "name": "fetch_metrics",
            "type": "processor",
            "class": "DBFetcher",
            "config": {
                "table": "operational_metrics",
                "output_field": "metrics",
                "filters": {
                    "department": "execution.steps.extract_report_params.data.department",
                    "date_range": "execution.steps.extract_report_params.data.date_range"
                }
            }
        },
        {
            "name": "generate_report",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "generate_report",
                "strategy": "single_pass",
                "temperature": 0.2,
                "output_field": "report_content"
            }
        },
        {
            "name": "render_pdf",
            "type": "custom",
            "class": "PDFRenderer",
            "config": {
                "content_field": "execution.steps.generate_report.data.report_content",
                "output_dir": "reports"
            }
        },
        {
            "name": "draft_report_email",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_report_ready",
                "tone": "professional"
            }
        },
        {
            "name": "send_report_email",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_name",
                "attach_field": "execution.steps.render_pdf.data.output_path"
            }
        }
    ],
    "on_failure": "log_and_alert",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'leave_checker',
    '{
    "agent_name": "leave_checker",
    "agent_version": "v1",
    "department": "HR",
    "risk_tier": "low",
    "approval": "none",
    "steps": [
        {
            "name": "extract_intent",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "employee_name",
                    "leave_type",
                    "date_range"
                ]
            }
        },
        {
            "name": "access_guard",
            "type": "custom",
            "class": "AccessGuard",
            "config": {
                "cross_person_min_level": 3
            }
        },
        {
            "name": "fetch_leave_record",
            "type": "extractor",
            "class": "DBExtractor",
            "config": {
                "table": "hr_leave_balances",
                "match_on": [
                    "email"
                ]
            }
        },
        {
            "name": "render_reply",
            "type": "processor",
            "class": "TemplateRenderer",
            "config": {
                "template": "templates/email/hr_reply.j2"
            }
        },
        {
            "name": "send_reply",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_email"
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'email_agent',
    '{
    "agent_name": "email_agent",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "medium",
    "approval": "single_confirm_if_low_confidence",
    "confidence_threshold": 0.85,
    "steps": [
        {
            "name": "summarise_attachments",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "summarise_attachment",
                "run_if": "task.has_attachments == true"
            }
        },
        {
            "name": "draft_reply",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_email_reply",
                "temperature": 0.3,
                "tone_rules": {
                    "IT": "direct",
                    "HR": "empathetic",
                    "Finance": "formal"
                }
            }
        },
        {
            "name": "score_confidence",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "self_rate_confidence",
                "output_field": "confidence_score"
            }
        },
        {
            "name": "compliance_check",
            "type": "extractor",
            "class": "DBExtractor",
            "config": {
                "service": "compliance_checker",
                "action_type": "send_email"
            }
        },
        {
            "name": "send_email",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_email",
                "log_audit": true
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'powerpoint_agent',
    '{
    "agent_name": "powerpoint_agent",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "medium",
    "approval": "single_confirm",
    "steps": [
        {
            "name": "select_template",
            "type": "processor",
            "class": "DBFetcher",
            "config": {
                "table": "templates/pptx/templates_meta.json",
                "match_on": [
                    "task_type"
                ]
            }
        },
        {
            "name": "generate_slide_json",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "generate_slides",
                "temperature": 0.4,
                "required_fields": [
                    "audience",
                    "purpose",
                    "key_message"
                ],
                "pause_if_missing": true
            }
        },
        {
            "name": "write_pptx",
            "type": "custom",
            "class": "PPTXWriter",
            "config": {
                "output_dir": "output/presentations",
                "naming": "{task_id}_{date}_{short_title}.pptx"
            }
        },
        {
            "name": "draft_email",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_email_reply",
                "tone": "professional"
            }
        },
        {
            "name": "email_file",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_name",
                "attach_field": "execution.steps.write_pptx.data.output_path"
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'meeting_scheduler',
    '{
    "agent_name": "meeting_scheduler",
    "agent_version": "v1",
    "department": "cross-dept",
    "risk_tier": "medium",
    "approval": "none",
    "steps": [
        {
            "name": "extract_participants",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "participant_names",
                    "participant_emails",
                    "preferred_duration",
                    "topic"
                ]
            }
        },
        {
            "name": "fetch_availability",
            "type": "extractor",
            "class": "DBExtractor",
            "config": {
                "service": "calendar_api",
                "look_ahead_days": 5
            }
        },
        {
            "name": "rank_slots",
            "type": "custom",
            "class": "SlotRanker",
            "config": {
                "max_proposals": 3,
                "scoring": "participant_overlap"
            }
        },
        {
            "name": "persist_meeting",
            "type": "custom",
            "class": "PersistMeeting",
            "config": {}
        },
        {
            "name": "send_invite",
            "type": "dispatcher",
            "class": "CalendarDispatcher",
            "config": {
                "monitor_rsvp": true,
                "template": "templates/email/meeting_invite.j2"
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'expense_tracker',
    '{
    "agent_name": "expense_tracker",
    "agent_version": "v1",
    "department": "Finance",
    "risk_tier": "medium",
    "approval": "none",
    "steps": [
        {
            "name": "extract_report_ref",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "report_id",
                    "employee_name",
                    "date_range"
                ]
            }
        },
        {
            "name": "access_guard",
            "type": "custom",
            "class": "AccessGuard",
            "config": {
                "cross_person_min_level": 3
            }
        },
        {
            "name": "fetch_expense_record",
            "type": "extractor",
            "class": "DBExtractor",
            "config": {
                "table": "finance_expense_reports",
                "access": "read_only",
                "match_on": [
                    "email",
                    "report_id"
                ]
            }
        },
        {
            "name": "check_anomalies",
            "type": "custom",
            "class": "AnomalyChecker",
            "config": {
                "duplicate_window_days": 30,
                "receipt_threshold_egp": 500,
                "on_anomaly": "escalate_to_finance_team"
            }
        },
        {
            "name": "draft_status_email",
            "type": "processor",
            "class": "LLMGenerator",
            "config": {
                "prompt_template": "draft_expense_status",
                "tone": "professional",
                "run_if": "execution.steps.check_anomalies.data.anomaly == false"
            }
        },
        {
            "name": "send_status_reply",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "task.requester_email",
                "run_if": "execution.steps.check_anomalies.data.anomaly == false"
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);

INSERT INTO agent_configs (agent_name, config, version, is_active)
VALUES (
    'onboarding_coordinator',
    '{
    "agent_name": "onboarding_coordinator",
    "agent_version": "v1",
    "department": "HR",
    "risk_tier": "medium",
    "approval": "manager_sign_off",
    "steps": [
        {
            "name": "extract_employee_details",
            "type": "extractor",
            "class": "NLPExtractor",
            "config": {
                "fields_to_extract": [
                    "employee_name",
                    "start_date",
                    "role",
                    "department",
                    "manager_name"
                ]
            }
        },
        {
            "name": "fetch_tooling_list",
            "type": "extractor",
            "class": "DBExtractor",
            "config": {
                "table": "tooling_list",
                "match_on": [
                    "department"
                ]
            }
        },
        {
            "name": "generate_checklist",
            "type": "processor",
            "class": "TemplateRenderer",
            "config": {
                "template": "templates/onboarding/{department}_onboarding.j2",
                "output_format": "pdf"
            }
        },
        {
            "name": "inject_access_tasks",
            "type": "custom",
            "class": "QueueInjector",
            "config": {
                "target_agent": "account_manager",
                "task_type": "access_provisioning",
                "one_task_per_tool": true
            }
        },
        {
            "name": "send_welcome_email",
            "type": "dispatcher",
            "class": "EmailDispatcher",
            "config": {
                "recipient_field": "execution.steps.extract_employee_details.data.employee_email",
                "require_approval": true,
                "attach_checklist": true
            }
        }
    ],
    "on_failure": "escalate",
    "outcome_signal": true
}'::jsonb,
    'v1',
    true
);
