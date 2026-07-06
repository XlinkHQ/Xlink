"use client";

import { DatabaseBackup } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { ApiError, downloadBackupDb, downloadUsersCsv, importBackupDb } from "@/lib/api";
import { SettingsRow } from "../settings";
import { SettingsSection } from "../settings-kit";

export function BackupScreen() {
  const [dbBusy, setDbBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    if (
      !(await confirmDialog({
        title: "Overwrite the database?",
        message: `Restoring "${file.name}" replaces ALL current data. Restart the panel afterwards.`,
        confirmLabel: "Restore",
        danger: true,
      }))
    )
      return;
    setImportBusy(true);
    try {
      await importBackupDb(file);
      toast("success", "Database restored — restart the panel to apply.");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restore failed.");
    } finally {
      setImportBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={DatabaseBackup}
        title="Backup & restore"
        description="Download database dumps, export users, or restore the panel from a previous backup."
      >
        <SettingsRow
          label="Download database"
          hint="A nightly backup runs automatically. Download the raw database now — Postgres .sql or SQLite .db (sudo only)."
        >
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            disabled={dbBusy}
            onClick={async () => {
              setDbBusy(true);
              try {
                await downloadBackupDb();
                toast("success", "Database dump downloaded.");
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : "Download failed.");
              } finally {
                setDbBusy(false);
              }
            }}
          >
            {dbBusy ? "…" : "Download"}
          </button>
        </SettingsRow>

        <SettingsRow
          label="Export users (CSV)"
          hint="Download every user as a spreadsheet — username, email, status, limit, expiry."
        >
          <button
            type="button"
            className="warp-tb-button"
            disabled={csvBusy}
            onClick={async () => {
              setCsvBusy(true);
              try {
                await downloadUsersCsv();
                toast("success", "Users CSV exported.");
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : "Export failed.");
              } finally {
                setCsvBusy(false);
              }
            }}
          >
            {csvBusy ? "…" : "Export"}
          </button>
        </SettingsRow>

        <SettingsRow
          label="Restore database"
          hint="Upload a .db / .sql dump to overwrite the current database. Destructive — sudo only."
        >
          <label className={`warp-tb-button warp-tb-button-danger${importBusy ? " is-busy" : ""}`} style={{ cursor: "pointer" }}>
            <input
              ref={inputRef}
              type="file"
              accept=".db,.sql,application/sql,application/x-sqlite3"
              className="hidden"
              disabled={importBusy}
              onChange={(e) => onImport(e.target.files?.[0])}
            />
            {importBusy ? "…" : "Upload"}
          </label>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
