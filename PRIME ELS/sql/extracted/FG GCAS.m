let
    GCASList =
        List.Buffer(
            List.Distinct(
                List.Transform(
                    Table.Column(#"SAP Plan PO", "FG GCAS"),
                    each Text.From(_)
                )
            )
        ),

    SQLList =
        Text.Combine(
            List.Transform(
                GCASList,
                each "'" & _ & "'"
            ),
            ","
        )
in
    SQLList