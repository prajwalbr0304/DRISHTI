#!/usr/bin/env python
"""Phase 1.5 verification: financial + chat + RBAC tables exist, are seeded,
FKs resolve, and the financial data shows flagged / structuring patterns."""
import os, psycopg2

conn = psycopg2.connect(host=os.environ["PGHOST"], port="5432", dbname="postgres",
                        user="postgres", password=os.environ["PGPASSWORD"], sslmode="require")
conn.autocommit = True
cur = conn.cursor()

def scalar(sql):
    cur.execute(sql); return cur.fetchone()[0]

print("=" * 70, "\nROW COUNTS (new tables)\n", "=" * 70, sep="")
for t in ["roles", "users", "role_permissions", "audit_logs", "FinancialAccount",
          "FinancialTransaction", "TransactionLink", "ChatSession", "ChatMessage",
          "VoiceTranscript", "SavedQuery"]:
    print(f"  {t:<24} {scalar(f'SELECT COUNT(*) FROM \"{t}\"'):>8,}")

print("\n" + "=" * 70, "\nRBAC SEED\n", "=" * 70, sep="")
cur.execute('SELECT "role_name","is_system" FROM "roles" ORDER BY "role_id"')
print("  roles:", [(r[0], r[1]) for r in cur.fetchall()])
print("  role_permissions:", scalar('SELECT COUNT(*) FROM "role_permissions"'),
      "( = 5 roles x 10 resources )")
cur.execute('SELECT r."role_name", COUNT(*) FILTER (WHERE rp."action"=\'write\') w '
            'FROM "roles" r JOIN "role_permissions" rp ON rp."role_id"=r."role_id" '
            'GROUP BY r."role_name" ORDER BY w DESC')
print("  write-grants per role:", [(r[0], r[1]) for r in cur.fetchall()])
cur.execute('SELECT "username","display_name" FROM "users" ORDER BY "user_id"')
print("  users:", [r[0] for r in cur.fetchall()])

print("\n" + "=" * 70, "\nFINANCIAL PATTERNS\n", "=" * 70, sep="")
print(f"  accounts flagged (mule/financier)   : {scalar('SELECT COUNT(*) FROM \"FinancialAccount\" WHERE \"IsFlagged\"'):,}")
print(f"  accounts linked to graph entity     : {scalar('SELECT COUNT(*) FROM \"FinancialAccount\" WHERE \"EntityID\" IS NOT NULL'):,}")
cur.execute('SELECT "AccountType", COUNT(*) FROM "FinancialAccount" GROUP BY "AccountType" ORDER BY 2 DESC')
print("  account types                       :", [(r[0], r[1]) for r in cur.fetchall()])
print(f"  transactions flagged                : {scalar('SELECT COUNT(*) FROM \"FinancialTransaction\" WHERE \"IsFlagged\"'):,}")
cur.execute('SELECT "FlagReason", COUNT(*) FROM "FinancialTransaction" WHERE "IsFlagged" GROUP BY "FlagReason" ORDER BY 2 DESC')
print("  flag reasons                        :", [(r[0], r[1]) for r in cur.fetchall()])
q_struct = 'SELECT COUNT(*) FROM "FinancialTransaction" WHERE "FlagReason" = \'structuring\' AND "Amount" < 50000'
print(f"  structuring txns < 50k threshold    : {scalar(q_struct):,}")
print(f"  txns with evidence case link        : {scalar('SELECT COUNT(*) FROM \"FinancialTransaction\" WHERE \"EvidenceCaseID\" IS NOT NULL'):,}")

print("\n  FK orphan checks (expect 0):")
checks = [
    ("FinTxn->SourceAccount", 'SELECT COUNT(*) FROM "FinancialTransaction" t WHERE NOT EXISTS (SELECT 1 FROM "FinancialAccount" a WHERE a."AccountID"=t."SourceAccountID")'),
    ("FinTxn->DestAccount", 'SELECT COUNT(*) FROM "FinancialTransaction" t WHERE NOT EXISTS (SELECT 1 FROM "FinancialAccount" a WHERE a."AccountID"=t."DestinationAccountID")'),
    ("FinTxn->EvidenceCase", 'SELECT COUNT(*) FROM "FinancialTransaction" t WHERE t."EvidenceCaseID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "CaseMaster" c WHERE c."CaseMasterID"=t."EvidenceCaseID")'),
    ("FinAcct->EntityGraph", 'SELECT COUNT(*) FROM "FinancialAccount" a WHERE a."EntityID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "EntityGraph" e WHERE e."EntityID"=a."EntityID")'),
    ("TxnLink->FinTxn", 'SELECT COUNT(*) FROM "TransactionLink" l WHERE NOT EXISTS (SELECT 1 FROM "FinancialTransaction" t WHERE t."TransactionID"=l."TransactionID")'),
    ("TxnLink->CaseMaster", 'SELECT COUNT(*) FROM "TransactionLink" l WHERE NOT EXISTS (SELECT 1 FROM "CaseMaster" c WHERE c."CaseMasterID"=l."CaseMasterID")'),
    ("ChatMsg->ChatSession", 'SELECT COUNT(*) FROM "ChatMessage" m WHERE NOT EXISTS (SELECT 1 FROM "ChatSession" s WHERE s."SessionID"=m."SessionID")'),
    ("ChatSession->users", 'SELECT COUNT(*) FROM "ChatSession" s WHERE s."UserID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."user_id"=s."UserID")'),
    ("ChatMsg->ModelVersion", 'SELECT COUNT(*) FROM "ChatMessage" m WHERE m."ModelVersionID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "ModelVersion" mv WHERE mv."ModelVersionID"=m."ModelVersionID")'),
]
tot = 0
for label, sql in checks:
    n = scalar(sql); tot += n
    print(f"    {label:<26} {n}")
print(f"    TOTAL ORPHANS: {tot}")

print("\n" + "=" * 70, "\nCHAT / CONTRACT\n", "=" * 70, sep="")
print(f"  assistant msgs w/ SQL + confidence + citations: "
      f"{scalar('SELECT COUNT(*) FROM \"ChatMessage\" WHERE \"Sender\"=\'assistant\' AND \"GeneratedSQL\" IS NOT NULL AND \"Confidence\" IS NOT NULL AND jsonb_array_length(\"CitedRecordIds\")>0')}")
q_kn = 'SELECT COUNT(*) FROM "ChatMessage" WHERE "Language" = \'kn\''
print(f"  Kannada messages                              : {scalar(q_kn)}")
print(f"  low-confidence voice transcripts              : {scalar('SELECT COUNT(*) FROM \"VoiceTranscript\" WHERE \"IsLowConfidence\"')}")

print("\n  Sample flagged structuring chain (one mule):")
cur.execute('''
  SELECT sa."HolderName" AS source, da."HolderName" AS mule, t."Amount", t."FlagReason"
  FROM "FinancialTransaction" t
  JOIN "FinancialAccount" sa ON sa."AccountID"=t."SourceAccountID"
  JOIN "FinancialAccount" da ON da."AccountID"=t."DestinationAccountID"
  WHERE t."FlagReason"='structuring'
  ORDER BY t."TransactionID" LIMIT 5''')
for r in cur.fetchall():
    print(f"    {r[0][:20]:<20} -> {r[1][:20]:<20} Rs {r[2]:>10,.2f}  [{r[3]}]")

conn.close()
print("\nDONE.")
