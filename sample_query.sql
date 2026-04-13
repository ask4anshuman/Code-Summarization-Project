-- Sample SQL demonstrating:
-- 1) CTEs
-- 2) Joins across tables
-- 3) Filters
-- 4) "Translation" of columns via aliases and CASE mappings

WITH recent_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        o.status_code,
        o.total_amount
    FROM sales.orders AS o
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2027-01-01'
      AND o.total_amount > 100
),
customer_profile AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.country_code,
        c.is_active
    FROM crm.customers AS c
    WHERE c.is_active = 1
),
order_lines AS (
    SELECT
        li.order_id,
        li.product_id,
        li.quantity,
        li.unit_price,
        (li.quantity * li.unit_price) AS line_total
    FROM sales.order_items AS li
)
SELECT
    ro.order_id AS order_number,                               -- alias translation
    ro.order_date AS purchase_date,                            -- alias translation
    CONCAT(cp.first_name, ' ', cp.last_name) AS customer_name,
    cp.country_code AS customer_country,

    p.product_name AS item_name,
    ol.quantity AS qty,
    ol.unit_price,
    ol.line_total,

    -- business translation: status codes -> readable labels
    CASE ro.status_code
        WHEN 'P' THEN 'Pending'
        WHEN 'S' THEN 'Shipped'
        WHEN 'D' THEN 'Delivered'
        WHEN 'C' THEN 'Cancelled'
        ELSE 'Unknown'
    END AS order_status_label,

    -- business translation: country codes -> region names
    CASE cp.country_code
        WHEN 'US' THEN 'North America'
        WHEN 'CA' THEN 'North America'
        WHEN 'GB' THEN 'Europe'
        WHEN 'DE' THEN 'Europe'
        WHEN 'IN' THEN 'Asia'
        ELSE 'Other'
    END AS region_name

FROM recent_orders AS ro
INNER JOIN customer_profile AS cp
    ON ro.customer_id = cp.customer_id
INNER JOIN order_lines AS ol
    ON ro.order_id = ol.order_id
LEFT JOIN inventory.products AS p
    ON ol.product_id = p.product_id

-- final filters
WHERE ro.status_code IN ('S', 'D')
  AND cp.country_code IN ('US', 'IN', 'DE')
  AND ol.quantity >= 1

ORDER BY ro.order_date DESC, ro.order_id, p.product_name;
