-- Read-only exploration queries for the local generate_report database (SQL Server Developer Edition).
-- Open in TablePlus (File > Open, or paste into a SQL tab) and run one statement at a time
-- (select it, then Cmd+Enter). Nothing here inserts, updates, deletes or executes procedures.

-- 1. Tables with approximate row counts
SELECT t.name AS table_name, SUM(p.rows) AS row_count
FROM sys.tables AS t
JOIN sys.partitions AS p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
GROUP BY t.name
ORDER BY t.name;

-- 2. Columns and data types for one table (change the table name)
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'employees'
ORDER BY ORDINAL_POSITION;

-- 3. Primary keys
SELECT tc.TABLE_NAME, kcu.COLUMN_NAME, tc.CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
ORDER BY tc.TABLE_NAME;

-- 4. Foreign keys (child column -> parent column)
SELECT OBJECT_NAME(fk.parent_object_id) + '.' + pc.name AS child_column,
       OBJECT_NAME(fk.referenced_object_id) + '.' + rc.name AS parent_column,
       fk.name AS constraint_name
FROM sys.foreign_keys AS fk
JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns AS pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.columns AS rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY child_column;

-- 5. Sample records
SELECT TOP (10) * FROM dbo.companies ORDER BY id;
SELECT TOP (10) * FROM dbo.employees ORDER BY id;
SELECT TOP (10) * FROM dbo.payroll ORDER BY payroll_month DESC, id;
SELECT TOP (10) * FROM dbo.report_jobs ORDER BY id;        -- the scheduled report jobs ("jobs")
SELECT TOP (10) id, job_id, status, current_step, started_at, completed_at FROM dbo.job_runs ORDER BY id DESC;
SELECT TOP (10) * FROM dbo.generated_files ORDER BY created_at DESC;   -- generated file metadata
SELECT id, username, full_name, department, title, permissions, is_active, updated_at FROM dbo.users;

-- 6. Column mapping data (stored as text/JSON on report jobs and uploaded queries)
SELECT id, title, source_type, source_key, column_mappings FROM dbo.report_jobs WHERE column_mappings IS NOT NULL;
SELECT id, original_name, approved_key, column_names FROM dbo.uploaded_queries;

-- 7. Payroll joined to employees and companies
SELECT TOP (20) c.company_name, e.employee_code, e.employee_name, e.department,
       p.payroll_month, p.basic_salary, p.allowances, p.deductions, p.net_salary, p.payment_status
FROM dbo.payroll AS p
JOIN dbo.employees AS e ON e.id = p.employee_id
JOIN dbo.companies AS c ON c.id = e.company_id
ORDER BY p.payroll_month DESC, c.company_name, e.employee_code;

-- 8. Stored procedures and their parameters
SELECT p.name AS procedure_name, pa.name AS parameter_name, TYPE_NAME(pa.user_type_id) AS parameter_type, pa.max_length
FROM sys.procedures AS p
LEFT JOIN sys.parameters AS pa ON pa.object_id = p.object_id
ORDER BY p.name, pa.parameter_id;

-- 9. Source code of the mapped payroll procedure (read-only; does not run it)
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.usp_GenerateMappedPayrollReport')) AS definition;
