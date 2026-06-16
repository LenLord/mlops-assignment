import httpx, json

questions = [
    ("What is the coordinates location of the circuits for Australian grand prix?", "formula_1"),
    ("List down Ajax's superpowers.", "superhero"),
    ("What is the average number of crimes committed in 1995 in regions where the number exceeds 4000 and the region has accounts that are opened starting from the year 1997?", "financial"),
    ("How many male clients in 'Hl.m. Praha' district?", "financial"),
    ("List the top five schools, by descending order, from the highest to the lowest, the most number of Enrollment (Ages 5-17). Please give their NCES school identification number.", "california_schools"),
]

for question, db in questions:
    print(f"\nQ: {question[:80]}... [{db}]")
    r = httpx.post("http://localhost:8001/answer", json={
        "question": question, "db": db,
        "tags": {"phase": "test", "db_id": db},
    }, timeout=120)
    data = r.json()
    print(f"  SQL:        {data.get('sql', '')[:100]}")
    print(f"  Rows:       {data.get('rows', [])[:3]}")
    print(f"  Iterations: {data.get('iterations')}")
    print(f"  OK:         {data.get('ok')}")
    if data.get("error"):
        print(f"  Error:      {data.get('error')}")
    if len(data.get("history", [])) > 1:
        print(f"  ** REVISED! History nodes: {[h['node'] for h in data['history']]}")
