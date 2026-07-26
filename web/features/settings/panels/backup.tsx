"use client";

import { DatabaseBackup } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { ApiError, downloadBackupDb, downloadUsersCsv, importBackupDb } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { SettingsRow } from "@/features/settings/save-context";
import { SettingsSection } from "@/shared/settings-kit";

export function BackupScreen() {
  const t = useT();
  const [dbBusy, setDbBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    if (
      !(await confirmDialog({
        title: t("backup.restoreConfirmTitle"),
        message: t("backup.restoreConfirmMessage", { name: file.name }),
        confirmLabel: t("backup.restore"),
        danger: true,
      }))
    )
      return;
    setImportBusy(true);
    try {
      await importBackupDb(file);
      toast("success", t("backup.restored"));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("backup.restoreFailed"));
    } finally {
      setImportBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={DatabaseBackup}
        title={t("backup.title")}
        description={t("backup.description")}
      >
        <SettingsRow
          label={t("backup.downloadDatabase")}
          hint={t("backup.downloadDatabaseHint")}
        >
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            disabled={dbBusy}
            onClick={async () => {
              setDbBusy(true);
              try {
                await downloadBackupDb();
                toast("success", t("backup.dumpDownloaded"));
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : t("backup.downloadFailed"));
              } finally {
                setDbBusy(false);
              }
            }}
          >
            {dbBusy ? "…" : t("backup.download")}
          </button>
        </SettingsRow>

        <SettingsRow
          label={t("backup.exportUsersCsv")}
          hint={t("backup.exportUsersCsvHint")}
        >
          <button
            type="button"
            className="warp-tb-button"
            disabled={csvBusy}
            onClick={async () => {
              setCsvBusy(true);
              try {
                await downloadUsersCsv();
                toast("success", t("backup.csvExported"));
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : t("backup.exportFailed"));
              } finally {
                setCsvBusy(false);
              }
            }}
          >
            {csvBusy ? "…" : t("backup.export")}
          </button>
        </SettingsRow>

        <SettingsRow
          label={t("backup.restoreDatabase")}
          hint={t("backup.restoreDatabaseHint")}
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
            {importBusy ? "…" : t("backup.upload")}
          </label>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
