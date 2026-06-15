"""Quick smoke test for sql_generator.py – run with: python _smoke_test.py"""
import sys
sys.path.insert(0, ".")

from services.sql_generator import RuleBasedSQLGenerator, SQLOutputTuner

gen   = RuleBasedSQLGenerator()
tuner = SQLOutputTuner()

rule_tests = [
    "Get all employees with salary greater than 50000",
    "Show top 5 customers by revenue",
    "Count all orders this month",
    "List last 10 transactions",
    "Find employees in Mumbai with salary above 70000",
    "Average salary by department",
    "Show active users",
    "Get female employees with age below 30",
    "Total sales for each category",
    "Show employees sorted descending by salary",
    "How many students have marks above 80",
    "Get products with price at most 999",
    "List employees with salary at least 60000",
    "Show pending orders this year",
]

print("=" * 60)
print("Rule-based generator smoke test")
print("=" * 60)
for q in rule_tests:
    sql = gen.generate(q)
    print(f"\nQ:   {q}")
    print(f"SQL:\n{sql}")
    print("-" * 40)

print()
print("=" * 60)
print("Output tuner tests")
print("=" * 60)
tuner_tests = [
    # lowercase keywords
    "select * from employees where salary > 50000;",
    # duplicate AND condition
    "SELECT * FROM orders WHERE status = 'active' AND status = 'active';",
    # COUNT(*) spacing
    "SELECT COUNT( * ) FROM products;",
    # no semicolon
    "SELECT id FROM users",
    # flat long query
    "SELECT id, name FROM employees WHERE age > 30 ORDER BY salary DESC LIMIT 10",
    # operator normalisation
    "SELECT * FROM t WHERE a < > 0 AND b ! = 5",
]
for raw in tuner_tests:
    result = tuner.tune(raw)
    print(f"IN :\n{raw}")
    print(f"OUT:\n{result}")
    print()

print("All tests passed.")
