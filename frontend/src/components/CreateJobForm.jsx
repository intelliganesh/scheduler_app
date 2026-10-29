import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import SearchableSelect from "./SearchableSelect";
import ConfirmDialog from "./ConfirmDialog";

const FORMAT_OPTIONS = [
  { value: "Text", label: "Text" },
  { value: "TextPhone", label: "TextPhone" },
  { value: "PhoneDash", label: "Phone (###-###-####)" },
  { value: "PhoneParens", label: "Phone (###) ###-####" },
  { value: "Date", label: "Date (YYYY-MM-DD)" },
  { value: "DateDMY", label: "Date (DD-MM-YYYY)" },
  { value: "DateMDY", label: "Date (MM/DD/YYYY)" },
  { value: "CurrencyUSD", label: "Currency ($)" },
  { value: "CurrencyINR", label: "Currency (₹)" },
  { value: "CurrencyEUR", label: "Currency (€)" },
];

const MAPPED_PROCEDURE = "mapped_employee_payroll_report";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPORT_SPLIT_OPTIONS = [
  { value: "file_name", label: "File Name" },
  { value: "client_id", label: "Client ID" },
  { value: "pay_date", label: "Pay Date" },
  { value: "file_client", label: "File Name + Client ID" },
  { value: "file_pay", label: "File Name + Pay Date" },
  { value: "client_pay", label: "Client ID + Pay Date" },
  { value: "file_client_pay", label: "File Name + Client ID + Pay Date" },
];

const DATABASE_FIELD_LABELS = {
  employee_code: "Employee Code",
  employee_name: "Employee Name",
  department: "Department",
  designation: "Designation",
  payroll_month: "Payroll Month",
  basic_salary: "Basic Salary",
  allowances: "Allowances",
  deductions: "Deductions",
  net_salary: "Net Salary",
  payment_status: "Payment Status",
  company_name: "Company Name",
  employee_count: "Employee Count",
  net_salary_total: "Net Salary Total",
  paydate: "Pay Date",
};

// Filter fields are limited to columns available from the payroll query.
// The list intentionally includes 15 practical employee/payroll fields.
const FILTER_FIELDS = [
  "employee_code",
  "employee_name",
  "department",
  "designation",
  "payroll_month",
  "paydate",
  "basic_salary",
  "allowances",
  "deductions",
  "net_salary",
  "payment_status",
  "company_name",
  "employee_id",
  "company_id",
  "is_active",
].map((value) => ({ value, label: databaseFieldLabel(value) }));
const NUMERIC_FILTER_FIELDS = new Set([
  "basic_salary",
  "allowances",
  "deductions",
  "net_salary",
  "employee_id",
  "company_id",
  "is_active",
]);
const DATE_FILTER_FIELDS = new Set(["payroll_month", "paydate"]);
const FILTER_OPERATORS = [
  { value: "eq", label: "Equal to (=)" },
  { value: "neq", label: "Not equal to (≠)" },
  { value: "gt", label: "Greater than (>)" },
  { value: "gte", label: "Greater than or equal (≥)" },
  { value: "lt", label: "Less than (<)" },
  { value: "lte", label: "Less than or equal (≤)" },
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Does not contain" },
  { value: "starts_with", label: "Starts with" },
  { value: "ends_with", label: "Ends with" },
  { value: "is_empty", label: "Is empty" },
  { value: "is_not_empty", label: "Is not empty" },
  { value: "is_null", label: "Is null" },
  { value: "is_not_null", label: "Is not null" },
  { value: "in", label: "In list (comma separated)" },
];

// Text-matching conditions apply only to text fields; the report query
// rejects them for numeric and date fields.
const TEXT_ONLY_OPERATORS = new Set([
  "contains",
  "not_contains",
  "starts_with",
  "ends_with",
]);
const COMPARISON_OPERATORS = new Set(["eq", "neq", "gt", "gte", "lt", "lte"]);
const VALUELESS_OPERATORS = new Set(["is_empty", "is_not_empty", "is_null", "is_not_null"]);

function filterOperatorsForField(field) {
  if (NUMERIC_FILTER_FIELDS.has(field) || DATE_FILTER_FIELDS.has(field)) {
    return FILTER_OPERATORS.filter(
      (operator) => !TEXT_ONLY_OPERATORS.has(operator.value) && !["is_empty", "is_not_empty"].includes(operator.value),
    );
  }
  return FILTER_OPERATORS.filter(
    (operator) => !COMPARISON_OPERATORS.has(operator.value) || ["eq", "neq"].includes(operator.value),
  );
}

function isPastSchedule(date, time) {
  const value = Date.parse(`${date}T${time}:00+05:30`);
  return !Number.isNaN(value) && value < Date.now() - 60000;
}

function filterRequiresValue(operator) {
  return !VALUELESS_OPERATORS.has(operator);
}

function filterInputType(field) {
  if (NUMERIC_FILTER_FIELDS.has(field)) return "number";
  return "text";
}

function formatMdyDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return match ? `${match[2]}/${match[3]}/${match[1]}` : "";
}

function parseMdyDate(value) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(value).trim());
  if (!match) return "";
  const [, month, day, year] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  if (
    date.getUTCFullYear() !== Number(year) ||
    date.getUTCMonth() + 1 !== Number(month) ||
    date.getUTCDate() !== Number(day)
  ) return "";
  return `${year}-${month}-${day}`;
}

function MdyDateInput({ value, onChange, ariaLabel, required = false }) {
  const pickerRef = useRef(null);
  const [draft, setDraft] = useState(() => formatMdyDate(value));
  useEffect(() => {
    setDraft(formatMdyDate(value));
  }, [value]);
  return (
    <div className="date-input-control">
      <input
        required={required}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        aria-label={ariaLabel}
        value={draft}
        placeholder="MM/DD/YYYY"
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          const parsed = parseMdyDate(next);
          if (parsed || !next.trim()) onChange(parsed);
        }}
      />
      <button
        type="button"
        className="date-picker-button"
        aria-label={`Open ${ariaLabel} picker`}
        onClick={() => pickerRef.current?.showPicker?.()}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3" y="4.5" width="18" height="16" rx="2" />
          <path d="M7 2.75v4M17 2.75v4M3 9h18M7 13h3M7 16.5h3M14 13h3M14 16.5h3" />
        </svg>
      </button>
      <input
        ref={pickerRef}
        className="native-date-picker"
        type="date"
        tabIndex={-1}
        aria-hidden="true"
        value={value || ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function normalizeFilterRule(rule) {
  const value = String(rule.value ?? "").trim();
  if (!filterRequiresValue(rule.operator)) return { ...rule, value: "" };
  if (rule.operator === "in")
    return {
      ...rule,
      value: value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
  return {
    ...rule,
    value: NUMERIC_FILTER_FIELDS.has(rule.field) ? Number(value) : value,
  };
}

function databaseFieldLabel(field) {
  return (
    DATABASE_FIELD_LABELS[field] ||
    String(field)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

function formatOptionsForField(field) {
  const name = String(field || "").toLowerCase();
  if (name.includes("phone") || name.includes("mobile"))
    return FORMAT_OPTIONS.filter((item) =>
      ["Text", "PhoneDash", "PhoneParens"].includes(item.value),
    );
  if (name.includes("date") || name.includes("month"))
    return FORMAT_OPTIONS.filter((item) =>
      ["Text", "Date", "DateDMY", "DateMDY"].includes(item.value),
    );
  if (
    name.includes("salary") ||
    name.includes("amount") ||
    name.includes("allowance") ||
    name.includes("deduction")
  )
    return FORMAT_OPTIONS.filter((item) =>
      ["Text", "CurrencyUSD", "CurrencyINR", "CurrencyEUR"].includes(
        item.value,
      ),
    );
  return FORMAT_OPTIONS.filter((item) =>
    ["Text"].includes(item.value),
  );
}

function MultiSelect({
  options,
  values,
  onAdd,
  onRemove,
  placeholder,
  ariaLabel,
}) {
  const available = options.filter(
    (option) => !values.includes(String(option.value)),
  );
  return (
    <div className="multi-select-control">
      <div className="multi-select-chips">
        {values.map((value) => {
          const item = options.find(
            (option) => String(option.value) === String(value),
          );
          return (
            <span className="email-chip" key={value}>
              {item?.label || value}
              <button
                type="button"
                aria-label={`Remove ${item?.label || value}`}
                onClick={() => onRemove(String(value))}
              >
                ×
              </button>
            </span>
          );
        })}
        <SearchableSelect
          value=""
          onChange={(value) => value && onAdd(String(value))}
          options={available}
          placeholder={placeholder}
          ariaLabel={ariaLabel}
        />
      </div>
    </div>
  );
}

const DEFAULT_VALUE_FIELD = "__default_value__";

function DatabaseFieldSelect({ value, defaultValue, onChange, onDefaultValueChange, options, ariaLabel }) {
  const selectedValue = defaultValue !== null && defaultValue !== undefined
    ? DEFAULT_VALUE_FIELD
    : value || "";
  return <div className="db-field-select">
    <SearchableSelect
      value={selectedValue}
      onChange={onChange}
      options={[...options, { value: DEFAULT_VALUE_FIELD, label: "Default" }]}
      placeholder="Select field"
      ariaLabel={ariaLabel}
    />
    {selectedValue === DEFAULT_VALUE_FIELD && (
      <input
        className="default-value-input"
        value={defaultValue || ""}
        onChange={(event) => onDefaultValueChange(event.target.value)}
        placeholder="Enter default value"
        aria-label={`Default value for ${ariaLabel}`}
      />
    )}
  </div>;
}

function UploadColumnList({ upload, mappedCount, totalCount, onChange }) {
  return (
    <div className="upload-column-list">
      <label>
        Upload column list <span className="required">*</span>
        <input
          type="file"
          accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
          onChange={onChange}
        />
      </label>
      <p className="muted small-note">
        Upload an Excel file with Record Type and Column Name columns.
      </p>
      {upload && (
        <p className="mapping-progress">
          {upload.original_name}: {mappedCount}/{totalCount} columns mapped
        </p>
      )}
    </div>
  );
}

function ManualEmailInput({
  clientId,
  values,
  draft,
  error,
  onDraftChange,
  onCommit,
  onRemove,
}) {
  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      onCommit(clientId, draft);
    }
  }
  function handlePaste(event) {
    const pasted = event.clipboardData.getData("text");
    if (pasted.includes(",")) {
      event.preventDefault();
      onCommit(clientId, pasted);
    }
  }
  return (
    <div className="manual-email-control">
      <div className="email-chips" aria-live="polite">
        {values.map((email) => (
          <span className="email-chip" key={email}>
            {email}
            <button
              type="button"
              aria-label={`Remove ${email}`}
              onClick={() => onRemove(clientId, email)}
            >
              ×
            </button>
          </span>
        ))}
        <input
          aria-label={`Manual email IDs for company ${clientId}`}
          value={draft}
          onChange={(event) => onDraftChange(clientId, event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder="Enter email address and press Enter"
        />
      </div>
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

function scheduleAtInKolkata(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || "");
  if (!match) throw new Error("Choose a valid schedule date and time.");
  const [, year, month, day, hour, minute] = match;
  const wallClock = new Date(
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
    ),
  );
  if (
    Number.isNaN(wallClock.getTime()) ||
    wallClock.getUTCFullYear() !== Number(year) ||
    wallClock.getUTCMonth() + 1 !== Number(month) ||
    wallClock.getUTCDate() !== Number(day) ||
    Number(hour) > 23 ||
    Number(minute) > 59
  ) {
    throw new Error("Choose a valid schedule date and time.");
  }
  return `${value}:00+05:30`;
}

function splitScheduleValue(value) {
  if (!value) return { date: "", time: "" };
  const text = String(value);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text);
  const parsed = new Date(hasZone ? text : `${text}+05:30`);
  if (Number.isNaN(parsed.getTime())) return { date: "", time: "" };
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(parsed);
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}

export default function CreateJobForm({
  token,
  onCreated,
  onCancel,
  embedded = false,
  editJob = null,
}) {
  const [companies, setCompanies] = useState([]);
  const [procedures, setProcedures] = useState([]);
  const [selectedClientIds, setSelectedClientIds] = useState([]);
  const [selectedClientEmails, setSelectedClientEmails] = useState({});
  const [emailDrafts, setEmailDrafts] = useState({});
  const [emailErrors, setEmailErrors] = useState({});
  const [form, setForm] = useState({
    title: "",
    schedule_date: "",
    schedule_time: "",
    company_id: "",
    source_key: "company_payroll_report",
    delimiter: ",",
    export_split_by: "file_name",
    schedule_type: "daily",
    weekly_day: "",
    monthly_day: "",
    sort_field: "",
    sort_direction: "asc",
    filter_field: "net_salary",
    filter_operator: "gt",
    filter_value: "",
    sort_rules: [],
    filter_rules: [],
  });
  const [upload, setUpload] = useState(null);
  const [mappingRows, setMappingRows] = useState([]);
  const [draggedField, setDraggedField] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [togglingEnabled, setTogglingEnabled] = useState(false);
  const [jobEnabled, setJobEnabled] = useState(editJob?.enabled ?? true);
  const [error, setError] = useState("");
  const selectedProcedure = procedures.find(
    (procedure) => procedure.key === form.source_key,
  );
  const availableFields = selectedProcedure?.allowed_fields || [];
  const isMappingJob = form.source_key === MAPPED_PROCEDURE;
  const mappedCount = mappingRows.filter(
    (row) => (row.db_column_names || []).length || row.default_value !== null && row.default_value !== undefined,
  ).length;
  const [step, setStep] = useState(1);
  const [discardOpen, setDiscardOpen] = useState(false);
  const isEditing = Boolean(editJob);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.companies(token), api.approvedProcedures(token)])
      .then(([companyList, procedureList]) => {
        setCompanies(companyList);
        setProcedures(procedureList);
      })
      .catch((err) => setError(err.message));
  }, [token]);
  useEffect(() => {
    if (!editJob || !companies.length) return;
    setJobEnabled(editJob.enabled);
    const schedule = splitScheduleValue(
      editJob.schedule_at || editJob.next_run_at,
    );
    const selections =
      editJob.client_selections && typeof editJob.client_selections === "object"
        ? editJob.client_selections
        : { [String(editJob.company_id)]: [] };
    const ids = Object.keys(selections);
    setSelectedClientIds(ids);
    setSelectedClientEmails(
      Object.fromEntries(
        ids.map((id) => [id, (selections[id] || []).map(String)]),
      ),
    );
    let mappings = [];
    try {
      mappings = editJob.column_mappings
        ? typeof editJob.column_mappings === "string"
          ? JSON.parse(editJob.column_mappings)
          : editJob.column_mappings
        : [];
    } catch {
      mappings = [];
    }
    setMappingRows(
      (mappings || []).map((item) => ({
        column_name: item.column_name || item.display_name,
        record_type: item.record_type || "D",
        db_column_names: Array.isArray(item.db_column_name)
          ? item.db_column_name
          : Array.isArray(item.database_field)
            ? item.database_field
            : [item.db_column_name || item.database_field || ""].filter(
                Boolean,
              ),
        default_value: item.default_value ?? null,
        format: item.format === "Default" ? "Text" : item.format || "Text",
      })),
    );
    let reportOptions = {};
    try {
      reportOptions =
        editJob.report_options && typeof editJob.report_options === "string"
          ? JSON.parse(editJob.report_options)
          : editJob.report_options || {};
    } catch {
      reportOptions = {};
    }
    setUpload(
      editJob.uploaded_query_id
        ? {
            id: editJob.uploaded_query_id,
            original_name: "Existing column list",
            column_names: mappings.map(
              (item) => item.column_name || item.display_name,
            ),
          }
        : null,
    );
    const sortRules =
      Array.isArray(reportOptions.sort_rules) && reportOptions.sort_rules.length
        ? reportOptions.sort_rules
        : reportOptions.sort_field
          ? [{ field: reportOptions.sort_field, direction: reportOptions.sort_direction || "asc" }]
          : [];
    const filterRules = Array.isArray(reportOptions.filter_rules)
      ? reportOptions.filter_rules
      : reportOptions.filter_value !== null &&
          reportOptions.filter_value !== undefined &&
          reportOptions.filter_value !== ""
        ? [
            {
              field: reportOptions.filter_field || "net_salary",
              operator: reportOptions.filter_operator || "gt",
              value: reportOptions.filter_value,
            },
          ]
        : [];
    const savedScheduleType =
      editJob.schedule_type === "once" ? "one_time" : editJob.schedule_type;
    const scheduleType = ["every_1_minute", "daily", "weekly", "monthly"].includes(
      savedScheduleType,
    )
      ? savedScheduleType
      : "daily";
    setForm((current) => ({
      ...current,
      title: editJob.title || editJob.display_name || "",
      schedule_date: schedule.date,
      schedule_time: schedule.time,
      company_id: String(editJob.company_id || ids[0] || ""),
      source_key: editJob.source_key || "company_payroll_report",
      delimiter: editJob.delimiter || ",",
      export_split_by: editJob.export_split_by || "file_name",
      schedule_type: scheduleType,
      weekly_day: editJob.day_of_week ?? "",
      monthly_day: editJob.day_of_month ?? "",
      sort_field: reportOptions.sort_field || "",
      sort_direction: reportOptions.sort_direction || "asc",
      filter_field: reportOptions.filter_field || "net_salary",
      filter_operator: reportOptions.filter_operator || "gt",
      filter_value: reportOptions.filter_value ?? "",
      sort_rules: sortRules,
      filter_rules: filterRules,
    }));
  }, [editJob, companies]);
  useEffect(() => {
    const valid = new Set(selectedClientIds);
    setSelectedClientEmails((current) =>
      Object.fromEntries(
        Object.entries(current).filter(([id]) => valid.has(id)),
      ),
    );
    setEmailDrafts((current) =>
      Object.fromEntries(
        Object.entries(current).filter(([id]) => valid.has(id)),
      ),
    );
    setEmailErrors((current) =>
      Object.fromEntries(
        Object.entries(current).filter(([id]) => valid.has(id)),
      ),
    );
  }, [token, selectedClientIds]);
  useEffect(() => {
    const dirty = Boolean(
      form.title ||
      form.schedule_date ||
      form.schedule_time ||
      selectedClientIds.length ||
      upload ||
      Object.values(selectedClientEmails).some((emails) => emails.length),
    );
    if (!dirty) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [
    form.title,
    form.schedule_date,
    form.schedule_time,
    selectedClientIds.length,
    selectedClientEmails,
    upload,
  ]);
  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }
  function updateRule(type, index, field, value) {
    setForm((current) => ({
      ...current,
      [type]: (current[type] || []).map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, [field]: value } : rule,
      ),
    }));
  }
  function updateFilterField(index, field) {
    setForm((current) => ({
      ...current,
      filter_rules: (current.filter_rules || []).map((rule, ruleIndex) =>
        ruleIndex === index
          ? {
              ...rule,
              field,
              operator: filterOperatorsForField(field)[0].value,
            }
          : rule,
      ),
    }));
  }
  function addRule(type, value) {
    setForm((current) => ({
      ...current,
      [type]: [...(current[type] || []), value],
    }));
  }
  function removeRule(type, index) {
    setForm((current) => {
      const remaining = (current[type] || []).filter(
        (_, ruleIndex) => ruleIndex !== index,
      );
      return {
        ...current,
        [type]: remaining,
        ...(type === "sort_rules" && !remaining.length ? { sort_field: "" } : {}),
      };
    });
  }
  function addClient(id) {
    setError("");
    setSelectedClientIds((current) => {
      const next = current.includes(id) ? current : [...current, id];
      update("company_id", next[0] || "");
      return next;
    });
  }
  function removeClient(id) {
    setSelectedClientIds((current) => {
      const next = current.filter((value) => value !== id);
      update("company_id", next[0] || "");
      return next;
    });
  }
  function addClientEmails(clientId, rawValue) {
    const candidates = rawValue
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (!candidates.length) return;
    const next = [...(selectedClientEmails[clientId] || [])];
    const seen = new Set(next.map((email) => email.toLowerCase()));
    let problem = "";
    for (const email of candidates) {
      if (!EMAIL_PATTERN.test(email)) {
        problem = `Enter a complete email address, for example name@company.in: ${email}`;
        continue;
      }
      if (seen.has(email.toLowerCase())) {
        problem = `Email address already added: ${email}`;
        continue;
      }
      seen.add(email.toLowerCase());
      next.push(email);
    }
    setSelectedClientEmails((current) => ({ ...current, [clientId]: next }));
    setEmailDrafts((current) => ({ ...current, [clientId]: "" }));
    setEmailErrors((current) => ({ ...current, [clientId]: problem }));
  }
  function removeClientEmail(clientId, email) {
    setSelectedClientEmails((current) => ({
      ...current,
      [clientId]: (current[clientId] || []).filter((value) => value !== email),
    }));
    setEmailErrors((current) => ({ ...current, [clientId]: "" }));
  }
  function setMapping(name, recordType, field) {
    setMappingRows((current) =>
      current.map((row) =>
        row.column_name === name && row.record_type === recordType
          ? {
              ...row,
              db_column_names: field && field !== DEFAULT_VALUE_FIELD ? [field] : [],
              default_value: field === DEFAULT_VALUE_FIELD ? (row.default_value ?? "") : null,
            }
          : row,
      ),
    );
  }
  function setDefaultValue(name, recordType, default_value) {
    setMappingRows((current) => current.map((row) =>
      row.column_name === name && row.record_type === recordType
        ? { ...row, default_value }
        : row,
    ));
  }
  function setRecordType(name, oldRecordType, record_type) {
    setMappingRows((current) =>
      current.map((row) =>
        row.column_name === name && row.record_type === oldRecordType
          ? { ...row, record_type }
          : row,
      ),
    );
  }
  function setFormat(name, recordType, format) {
    setMappingRows((current) =>
      current.map((row) =>
        row.column_name === name && row.record_type === recordType
          ? { ...row, format }
          : row,
      ),
    );
  }
  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setMessage("");
    try {
      const result = await api.uploadQuery(token, file);
      const parsed =
        typeof result.column_names === "string"
          ? JSON.parse(result.column_names)
          : result.column_names;
      const rows = (parsed || []).map((item) =>
        typeof item === "string"
          ? {
              column_name: item,
              record_type: "D",
              db_column_names: [],
              default_value: null,
              format: "Text",
            }
          : {
              column_name: item.column_name || item.display_name,
              record_type: String(item.record_type || "D").toUpperCase(),
              db_column_names: Array.isArray(item.db_column_name)
                ? item.db_column_name
                : Array.isArray(item.database_field)
                  ? item.database_field
                  : [item.db_column_name || item.database_field || ""].filter(
                      Boolean,
                    ),
              default_value: item.default_value ?? null,
              format: item.format === "Default" ? "Text" : item.format || "Text",
            },
      );
      setUpload({
        id: result.id,
        original_name: result.original_name,
        column_names: rows.map((row) => row.column_name),
      });
      update("source_key", MAPPED_PROCEDURE);
      setMappingRows(rows);
      setMessage(
        `${rows.length} columns loaded. Map each one to an approved field.`,
      );
    } catch (err) {
      event.target.value = "";
      setError(err.message);
    }
  }
  function drop(name, recordType, event) {
    event.preventDefault();
    if (draggedField) setMapping(name, recordType, draggedField);
    setDraggedField("");
  }
  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    // Keep scheduling strictly behind the review step. This also protects
    // against an accidental Enter/native-control submit while on Step 4.
    if (step !== 4) {
      nextStep();
      return;
    }
    if (!selectedClientIds.length) {
      setError("Select at least one company/client before scheduling.");
      return;
    }
    if (!form.source_key) {
      setError("The default report procedure is not available.");
      return;
    }
    if (isMappingJob && !upload) {
      setError("Upload a column list before scheduling.");
      return;
    }
    try {
      setSaving(true);
      const schedule_at = scheduleAtInKolkata(
        `${form.schedule_date}T${form.schedule_time}`,
      );
      const clientSelections = Object.fromEntries(
        selectedClientIds.map((clientId) => [
          String(clientId),
          (selectedClientEmails[clientId] || []).map(String),
        ]),
      );
      const payload = {
        title: form.title,
        display_name: form.title,
        schedule_at,
        company_id: Number(selectedClientIds[0]),
        source_type: "procedure",
        source_key: form.source_key,
        uploaded_query_id: upload?.id || null,
        column_mappings: isMappingJob
          ? mappingRows.map((row) => ({
              column_name: row.column_name,
              display_name: row.column_name,
              record_type: row.record_type,
              db_column_name: row.db_column_names || [],
              database_field: row.db_column_names || [],
              default_value: row.default_value,
              format: row.format || "Text",
              format_pattern: null,
            }))
          : null,
        delimiter: form.delimiter,
        export_split_by: form.export_split_by,
        schedule_type: form.schedule_type,
        weekly_day: form.weekly_day === "" ? null : Number(form.weekly_day),
        monthly_day: form.monthly_day === "" ? null : Number(form.monthly_day),
        sort_field: form.sort_field || null,
        sort_direction: form.sort_direction,
        filter_field: form.filter_field || null,
        filter_operator: form.filter_operator,
        filter_value:
          form.filter_value === "" ? null : Number(form.filter_value),
        sort_rules: (form.sort_rules || []).filter((rule) => rule.field),
        filter_rules: (form.filter_rules || [])
          .filter(
            (rule) =>
              rule.field &&
              (filterRequiresValue(rule.operator)
                ? rule.value !== "" && rule.value !== null
                : true),
          )
          .map(normalizeFilterRule),
        client_selections: clientSelections,
        recipients: [],
        enabled: jobEnabled,
      };
      if (isEditing) await api.updateJob(token, editJob.id, payload);
      else await api.createJob(token, payload);
      setMessage(
        isEditing ? "Job updated successfully." : "Job created and scheduled.",
      );
      if (isEditing) onCreated?.();
      else {
        setForm((current) => ({
          ...current,
          title: "",
          schedule_date: "",
          schedule_time: "",
          company_id: "",
          source_key: "company_payroll_report",
          delimiter: ",",
          export_split_by: "file_name",
          schedule_type: "daily",
          weekly_day: "",
          monthly_day: "",
          sort_field: "",
          sort_direction: "asc",
          filter_field: "net_salary",
          filter_operator: "gt",
          filter_value: "",
          sort_rules: [],
          filter_rules: [],
        }));
        setSelectedClientIds([]);
        setSelectedClientEmails({});
        setEmailDrafts({});
        setEmailErrors({});
        setUpload(null);
        setMappingRows([]);
        onCreated?.();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }
  const validateStep = (target) => {
    setError("");
    if (
      target > 1 &&
      (!form.title.trim() ||
        !form.source_key ||
        !form.schedule_date ||
        !form.schedule_time)
    )
      return "Complete job name and execution date/time.";
    if (target > 1 && form.schedule_type === "weekly" && form.weekly_day === "")
      return "Choose a weekday.";
    if (
      target > 1 &&
      form.schedule_type === "monthly" &&
      form.monthly_day === ""
    )
      return "Choose a day of the month.";
    if (target > 1 && (isMappingJob || !isEditing) && !upload)
      return "Upload a column list before continuing.";
    const originalSchedule = isEditing
      ? splitScheduleValue(editJob.schedule_at || editJob.next_run_at)
      : null;
    const scheduleChanged =
      !originalSchedule ||
      originalSchedule.date !== form.schedule_date ||
      originalSchedule.time !== form.schedule_time;
    if (
      target > 1 &&
      scheduleChanged &&
      isPastSchedule(form.schedule_date, form.schedule_time)
    )
      return "Execution date and time must be in the future (Asia/Kolkata).";
    if (target > 2 && isMappingJob && mappedCount < mappingRows.length)
      return "Map every uploaded column to at least one database field.";
    if (
      target > 2 &&
      isMappingJob &&
      mappingRows.some(
        (row) => row.default_value !== null && row.default_value !== undefined && !String(row.default_value).trim(),
      )
    ) return "Enter a default value for every column mapped as Default.";
    return "";
  };
  function nextStep() {
    const problem = validateStep(step + 1);
    if (problem) {
      setError(problem);
      return;
    }
    setStep((value) => Math.min(4, value + 1));
  }
  function handleNext(event) {
    event.preventDefault();
    event.stopPropagation();
    nextStep();
  }
  function cancelWizard() {
    setDiscardOpen(true);
  }
  async function toggleJobEnabled() {
    if (!editJob) return;
    try {
      setTogglingEnabled(true);
      setError("");
      const updated = await api.toggleJob(token, editJob.id, !jobEnabled);
      setJobEnabled(updated.enabled);
      setMessage(updated.enabled ? "Job enabled." : "Job disabled.");
    } catch (err) {
      setError(err.message);
    } finally {
      setTogglingEnabled(false);
    }
  }
  const companyLabel = (id) =>
    companies.find((company) => String(company.id) === String(id))
      ?.company_name || id;
  const scheduleLabel = {
    one_time: "One Time",
    every_1_minute: "Every 1 Minute",
    every_2_minutes: "Every 2 Minutes",
    hourly_1: "Every 1 Hour",
    hourly_2: "Every 2 Hours",
    hourly_4: "Every 4 Hours",
    daily: "Daily",
    weekly: "Weekly",
    monthly: "Monthly",
  }[form.schedule_type];
  const exportSplitLabel =
    EXPORT_SPLIT_OPTIONS.find((item) => item.value === form.export_split_by)
      ?.label || "File Name";
  return (
    <section className="wizard-page">
      <div className="wizard-header">
        <div>
          <p className="eyebrow">Scheduling</p>
          <h2>{isEditing ? "Edit Job" : "New Job"}</h2>
          <p className="muted">
            {isEditing
              ? "Update the job configuration and schedule."
              : "Create, configure, and schedule a report job."}
          </p>
        </div>
        <div className="wizard-header-actions">
          {isEditing && (
            <button
              type="button"
              className={`small-button ${jobEnabled ? "disable-job-button" : "enable-job-button"}`}
              disabled={togglingEnabled}
              onClick={toggleJobEnabled}
            >
              {togglingEnabled ? "Updating…" : jobEnabled ? "Disable" : "Enable"}
            </button>
          )}
        </div>
      </div>
      <div className="wizard-steps">
        {[
          "Job Details",
          "Column Mapping",
          "Filtering & Sorting",
          "Clients & Emails",
        ].map((label, index) => (
          <button
            type="button"
            key={label}
            className={
              step === index + 1
                ? "wizard-step active"
                : step > index + 1
                  ? "wizard-step complete"
                  : "wizard-step"
            }
            onClick={() => step > index + 1 && setStep(index + 1)}
            disabled={step <= index + 1}
          >
            {index + 1}
            <span>{label}</span>
          </button>
        ))}
      </div>
      <section className="card wizard-card">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (step === 4) submit(event);
            else nextStep();
          }}
        >
          {step === 1 && (
            <div className="wizard-section">
              <h3>Job Details &amp; Scheduling</h3>
              <label>
                Job Name <span className="required">*</span>
                <input
                  required
                  value={form.title}
                  onChange={(event) => update("title", event.target.value)}
                  placeholder="e.g. Monthly payroll summary"
                />
              </label>
              <label>
                Schedule Type <span className="required">*</span>
                <SearchableSelect
                  value={form.schedule_type}
                  onChange={(value) => update("schedule_type", value)}
                  options={[
                    { value: "every_1_minute", label: "Every 1 Minute" },
                    { value: "daily", label: "Daily" },
                    { value: "weekly", label: "Weekly" },
                    { value: "monthly", label: "Monthly" },
                  ]}
                  placeholder="Select schedule type"
                  ariaLabel="Schedule Type"
                />
              </label>
              <div className="schedule-date-time-grid">
                <label>
                  Execution Date <span className="required">*</span>
                  <MdyDateInput
                    required
                    ariaLabel="Execution Date"
                    value={form.schedule_date}
                    onChange={(value) => update("schedule_date", value)}
                  />
                </label>
                <label>
                  Execution Time <span className="required">*</span>
                  <input
                    required
                    type="time"
                    value={form.schedule_time}
                    onChange={(event) =>
                      update("schedule_time", event.target.value)
                    }
                  />
                </label>
              </div>
              {(form.schedule_type === "weekly" ||
                form.schedule_type === "monthly") && (
                <div className="schedule-options-panel">
                  <p className="schedule-options-title">
                    {form.schedule_type === "weekly"
                      ? "Weekly schedule"
                      : "Monthly schedule"}
                  </p>
                  {form.schedule_type === "weekly" ? (
                    <label>
                      Day of Week <span className="required">*</span>
                      <SearchableSelect
                        value={form.weekly_day}
                        onChange={(value) => update("weekly_day", value)}
                        options={[
                          "Sunday",
                          "Monday",
                          "Tuesday",
                          "Wednesday",
                          "Thursday",
                          "Friday",
                          "Saturday",
                        ].map((label, value) => ({ value, label }))}
                        placeholder="Select day"
                        ariaLabel="Day of Week"
                      />
                    </label>
                  ) : (
                    <label>
                      Day of Month <span className="required">*</span>
                      <SearchableSelect
                        value={form.monthly_day}
                        onChange={(value) => update("monthly_day", value)}
                        options={Array.from({ length: 31 }, (_, index) => ({
                          value: index + 1,
                          label: String(index + 1),
                        }))}
                        placeholder="Select day"
                        ariaLabel="Day of Month"
                      />
                    </label>
                  )}
                </div>
              )}
              <div className="export-settings-inline">
                <label>
                  Select Delimiter{" "}
                  <SearchableSelect
                    value={form.delimiter || ","}
                    onChange={(value) => update("delimiter", value)}
                    options={[
                      { value: ",", label: "Comma (,)" },
                      { value: "|", label: "Pipe (|)" },
                      { value: ";", label: "Semicolon (;)" },
                      { value: "\t", label: "Tab (\\t)" },
                    ]}
                    ariaLabel="Select Delimiter"
                  />
                </label>
                <label>
                  Export Split By{" "}
                  <SearchableSelect
                    value={form.export_split_by || "file_name"}
                    onChange={(value) => update("export_split_by", value)}
                    options={EXPORT_SPLIT_OPTIONS}
                    ariaLabel="Export Split By"
                  />
                </label>
              </div>
              <UploadColumnList
                upload={upload}
                mappedCount={mappedCount}
                totalCount={mappingRows.length}
                onChange={handleUpload}
              />
            </div>
          )}
          {step === 4 && (
            <div className="wizard-section">
              <h3>Clients &amp; Email Recipients</h3>
              <p className="step-helper">
                Select one or more companies, then add optional email recipients
                for each selected company.
              </p>
              <div className="client-step-content">
                <label>
                  Company / Client <span className="required">*</span>
                  <MultiSelect
                    options={companies.map((company) => ({
                      value: company.id,
                      label: `${company.company_name} (Client ID: ${company.id})`,
                    }))}
                    values={selectedClientIds}
                    onAdd={addClient}
                    onRemove={removeClient}
                    placeholder="Search companies / clients"
                    ariaLabel="Select Companies / Clients"
                  />
                </label>
                {selectedClientIds.length ? (
                  <div
                    className="client-email-list"
                    aria-label="Manual email recipients by company"
                  >
                    {selectedClientIds.map((clientId) => {
                      const client = companies.find(
                        (item) => String(item.id) === String(clientId),
                      );
                      return (
                        <div className="client-email-row" key={clientId}>
                          <div className="client-email-company">
                            <strong>{client?.company_name || "Client"}</strong>
                            <span>Client ID: {clientId}</span>
                          </div>
                          <ManualEmailInput
                            clientId={String(clientId)}
                            values={selectedClientEmails[clientId] || []}
                            draft={emailDrafts[clientId] || ""}
                            error={emailErrors[clientId] || ""}
                            onDraftChange={(id, value) => {
                              setEmailDrafts((current) => ({
                                ...current,
                                [id]: value,
                              }));
                              if (emailErrors[id])
                                setEmailErrors((current) => ({
                                  ...current,
                                  [id]: "",
                                }));
                            }}
                            onCommit={addClientEmails}
                            onRemove={removeClientEmail}
                          />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="client-empty-state">
                    <strong>No companies selected yet</strong>
                    <span>
                      Select a company above to configure its email recipients.
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="wizard-section mapping-wizard-section">
              <h3>Excel Upload &amp; Column Mapping</h3>
              <div className="mapping-panel">
                {upload && (
                  <>
                    <p className="mapping-progress">
                      {upload.original_name}: {mappedCount}/{mappingRows.length}{" "}
                      columns mapped
                    </p>
                    <div className="mapping-table-wrap">
                      <table className="mapping-table">
                        <thead>
                          <tr>
                            <th>Column Name</th>
                            <th>Record Type</th>
                            <th>DB Column Name</th>
                            <th>Format</th>
                          </tr>
                        </thead>
                        <tbody>
                          {mappingRows.map((row) => (
                            <tr
                              key={`${row.column_name}-${row.record_type}`}
                              onDragOver={(event) => event.preventDefault()}
                              onDrop={(event) =>
                                drop(row.column_name, row.record_type, event)
                              }
                            >
                              <td className="mapping-cell mapping-readonly">
                                {row.column_name}
                              </td>
                              <td className="mapping-cell">
                                <select
                                  className={`record-type-select record-type-${row.record_type}`}
                                  value={row.record_type}
                                  onChange={(event) =>
                                    setRecordType(
                                      row.column_name,
                                      row.record_type,
                                      event.target.value,
                                    )
                                  }
                                >
                                  <option value="H">Header</option>
                                  <option value="D">Detail</option>
                                  <option value="T">Trailer</option>
                                </select>
                              </td>
                              <td className="mapping-cell">
                                <DatabaseFieldSelect
                                  value={row.db_column_names?.[0] || ""}
                                  defaultValue={row.default_value}
                                  onChange={(value) => setMapping(
                                    row.column_name,
                                    row.record_type,
                                    value,
                                  )}
                                  onDefaultValueChange={(value) => setDefaultValue(
                                    row.column_name,
                                    row.record_type,
                                    value,
                                  )}
                                  options={availableFields.map((field) => ({
                                    value: field,
                                    label: databaseFieldLabel(field),
                                  }))}
                                  ariaLabel={`Database field for ${row.column_name}`}
                                />
                              </td>
                              <td className="mapping-cell">
                                <SearchableSelect
                                  value={row.format || "Text"}
                                  onChange={(value) =>
                                    setFormat(
                                      row.column_name,
                                      row.record_type,
                                      value,
                                    )
                                  }
                                  options={formatOptionsForField(
                                    (row.db_column_names || []).join(" ") ||
                                      row.column_name,
                                  )}
                                  placeholder="Select format"
                                  ariaLabel={`Format for ${row.column_name}`}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
          {step === 3 && (
            <div className="wizard-section">
              <h3>Filtering &amp; Sorting</h3>
              <p className="step-helper">
                Add one or more filters first, then choose one or more sort
                rules for the report output.
              </p>
              <div className="sort-filter-card sort-filter-card-full">
                <h4>Filters</h4>
                {(form.filter_rules || []).map((rule, index) => (
                  <div className="rule-row" key={`filter-${index}`}>
                    <SearchableSelect
                      value={rule.field || "net_salary"}
                      onChange={(value) => updateFilterField(index, value)}
                      options={FILTER_FIELDS}
                      ariaLabel={`Filter field ${index + 1}`}
                    />
                    <SearchableSelect
                      value={rule.operator || "gt"}
                      onChange={(value) =>
                        updateRule("filter_rules", index, "operator", value)
                      }
                      options={filterOperatorsForField(
                        rule.field || "net_salary",
                      )}
                      ariaLabel={`Filter condition ${index + 1}`}
                    />
                    {DATE_FILTER_FIELDS.has(rule.field || "net_salary") ? (
                      <MdyDateInput
                        ariaLabel={`Filter date value ${index + 1}`}
                        value={rule.value ?? ""}
                        onChange={(value) => updateRule("filter_rules", index, "value", value)}
                      />
                    ) : (
                      <input
                        type={filterInputType(rule.field || "net_salary")}
                        step={
                          NUMERIC_FILTER_FIELDS.has(rule.field || "net_salary")
                            ? "0.01"
                            : undefined
                        }
                        value={rule.value ?? ""}
                        onChange={(event) =>
                          updateRule(
                            "filter_rules",
                            index,
                            "value",
                            event.target.value,
                          )
                        }
                        placeholder={
                          NUMERIC_FILTER_FIELDS.has(rule.field || "net_salary")
                            ? "Value, e.g. 0"
                            : "Enter a value"
                        }
                      />
                    )}
                    <button
                      type="button"
                      className="small-button secondary"
                      onClick={() => removeRule("filter_rules", index)}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="small-button secondary"
                  onClick={() =>
                    addRule("filter_rules", {
                      field: "net_salary",
                      operator: "gt",
                      value: "",
                    })
                  }
                >
                  + Add filter
                </button>
              </div>
              <div className="sort-filter-card sort-filter-card-full">
                <h4>Sort rules</h4>
                {(form.sort_rules || []).map((rule, index) => (
                  <div className="rule-row" key={`sort-${index}`}>
                    <SearchableSelect
                      value={rule.field || "company_name"}
                      onChange={(value) =>
                        updateRule("sort_rules", index, "field", value)
                      }
                      options={[
                        { value: "company_name", label: "Company Name" },
                        { value: "employee_code", label: "Employee Code" },
                        { value: "employee_name", label: "Employee Name" },
                        { value: "payroll_month", label: "Payroll Month" },
                        { value: "net_salary", label: "Net Salary" },
                      ]}
                      ariaLabel={`Sort field ${index + 1}`}
                    />
                    <SearchableSelect
                      value={rule.direction || "asc"}
                      onChange={(value) =>
                        updateRule("sort_rules", index, "direction", value)
                      }
                      options={[
                        { value: "asc", label: "Ascending" },
                        { value: "desc", label: "Descending" },
                      ]}
                      ariaLabel={`Sort direction ${index + 1}`}
                    />
                    <button
                      type="button"
                      className="small-button secondary"
                      onClick={() => removeRule("sort_rules", index)}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="small-button secondary"
                  onClick={() =>
                    addRule("sort_rules", {
                      field: "employee_name",
                      direction: "asc",
                    })
                  }
                >
                  + Add sort rule
                </button>
              </div>
            </div>
          )}

          {error && <p className="error wizard-error">{error}</p>}
          <div className="wizard-actions">
            <button
              type="button"
              className="small-button secondary"
              onClick={() =>
                step === 1 ? cancelWizard() : setStep((value) => value - 1)
              }
            >
              {step === 1 ? "Cancel" : "Back"}
            </button>
            {step < 4 ? (
              <button type="button" onClick={handleNext}>
                Next
              </button>
            ) : (
              <button type="submit" disabled={saving}>
                {saving
                  ? isEditing
                    ? "Saving…"
                    : "Scheduling…"
                  : isEditing
                    ? "Save Changes"
                    : "Create & Schedule Job"}
              </button>
            )}
          </div>
        </form>
      </section>
      <ConfirmDialog
        open={discardOpen}
        title={isEditing ? "Discard job edits?" : "Discard unsaved job?"}
        message={
          isEditing
            ? "Your changes will be lost."
            : "Your unsaved job will be discarded."
        }
        confirmLabel="Discard"
        danger
        onCancel={() => setDiscardOpen(false)}
        onConfirm={() => {
          setDiscardOpen(false);
          onCancel?.();
        }}
      />
    </section>
  );
}
