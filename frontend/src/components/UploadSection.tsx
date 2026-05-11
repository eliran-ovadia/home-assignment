// Drag-and-drop .xlsx uploader. On 200 → toast the summary + bump refresh.
// On 422 with rejected_rows → render a per-row error table so the user can
// fix the file and retry.

import { InboxOutlined } from "@ant-design/icons";
import {
  Alert,
  Card,
  Descriptions,
  Spin,
  Table,
  Typography,
  Upload,
  message,
} from "antd";
import type { RcFile } from "antd/es/upload";
import { useState } from "react";
import {
  ApiError,
  isRejectedRows,
  uploadTransactions,
} from "../api/client";
import type {
  RejectedRow,
  UploadResponse,
} from "../types";

interface UploadSectionProps {
  onUploaded: () => void;
}

export function UploadSection({ onUploaded }: UploadSectionProps) {
  const [busy, setBusy] = useState(false);
  const [lastSummary, setLastSummary] = useState<UploadResponse | null>(null);
  const [rejectedRows, setRejectedRows] = useState<RejectedRow[] | null>(null);
  const [genericError, setGenericError] = useState<string | null>(null);

  const handleUpload = async (file: RcFile): Promise<boolean> => {
    setBusy(true);
    setLastSummary(null);
    setRejectedRows(null);
    setGenericError(null);
    try {
      const response = await uploadTransactions(file);
      setLastSummary(response);
      message.success(
        `Upload complete: ${response.summary.transactions_loaded} transactions`,
      );
      onUploaded();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 422 && isRejectedRows(err.body)) {
          setRejectedRows(err.body.rejected_rows);
        } else {
          setGenericError(err.message);
        }
      } else {
        setGenericError(String(err));
      }
    } finally {
      setBusy(false);
    }
    // Returning false prevents the Upload widget from displaying its own
    // request status — we render everything ourselves.
    return false;
  };

  return (
    <Card title="Upload transactions">
      <Spin spinning={busy}>
        <Upload.Dragger
          accept=".xlsx"
          multiple={false}
          showUploadList={false}
          beforeUpload={handleUpload}
          disabled={busy}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            Drop an .xlsx file here, or click to browse
          </p>
          <p className="ant-upload-hint">
            10 MB max · expected columns: ClientId, TransactionId, ISIN, Action,
            Quantity, Price, Timestamp
          </p>
        </Upload.Dragger>
      </Spin>

      {lastSummary && (
        <Descriptions
          column={3}
          size="small"
          style={{ marginTop: 16 }}
          bordered
        >
          <Descriptions.Item label="Upload ID">{lastSummary.upload_id}</Descriptions.Item>
          <Descriptions.Item label="Transactions">
            {lastSummary.summary.transactions_loaded}
          </Descriptions.Item>
          <Descriptions.Item label="Positions">
            {lastSummary.summary.positions_computed}
          </Descriptions.Item>
          <Descriptions.Item label="Violations">
            {lastSummary.summary.violations_detected}
          </Descriptions.Item>
        </Descriptions>
      )}

      {rejectedRows && (
        <>
          <Alert
            type="error"
            style={{ marginTop: 16 }}
            message="Upload rejected"
            description="Every row must validate before the file is accepted. Fix the rows below and try again."
          />
          <Table<RejectedRow>
            size="small"
            style={{ marginTop: 12 }}
            rowKey={(row) => `${row.row_number}-${row.column}`}
            dataSource={rejectedRows}
            pagination={false}
            columns={[
              { title: "Row", dataIndex: "row_number", key: "row_number", width: 80 },
              {
                title: "Transaction ID",
                dataIndex: "transaction_id",
                key: "transaction_id",
                render: (value: string | null) => value ?? <Typography.Text type="secondary">—</Typography.Text>,
              },
              { title: "Column", dataIndex: "column", key: "column", width: 140 },
              { title: "Reason", dataIndex: "reason", key: "reason" },
            ]}
          />
        </>
      )}

      {genericError && (
        <Alert
          type="error"
          style={{ marginTop: 16 }}
          message="Upload failed"
          description={genericError}
        />
      )}
    </Card>
  );
}
