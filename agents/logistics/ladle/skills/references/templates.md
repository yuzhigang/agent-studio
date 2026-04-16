# Rule Category Templates

## 1. Compatibility Rules
Ensures physical attributes don't conflict with planning roles.
- **Paradigm**: `IF Subject.Physical.A satisfies X THEN Subject.Planning.B MUST/MUST NOT be Y`.
- **Example**: `IF Phys.Surface == 'S4' AND Plan.Role == 'Transition' THEN Veto`.

## 2. Sequence Rules
Ensures production stability and avoids abrupt changes.
- **Paradigm**: `IF Current.Attr and Previous.Attr relationship satisfies X THEN Action`.
- **Example**: `IF Cur.Role == 'Transition' AND Pre.Role == 'Transition' AND Cur.Width == Pre.Width THEN Veto`.

## 3. Aggregation Rules
Controls the structure and proportions of a whole Rolling Unit.
- **Paradigm**: `IF Sum/Count(Items in Unit where Filter) [Operator] Threshold THEN Action`.
- **Example**: `IF Sum(Weight where Thickness <= 0.6) > 1500 THEN Veto`.

## Expression Structure (LHS)
`[Left Operand] [Operator] [Right Operand]`

- **Operators**: `>`, `<`, `=`, `!=`, `In`, `NotIn`, `Contains`, `AND`, `OR`.
- **Aggregation Functions**: `Sum`, `Count`, `Avg`, `Max`, `Min`.
