// First-visit gate: capture the user's corporate email once, store it in
// localStorage via `api/client.ts`, and call `onSubmit` so the surrounding
// app can refresh. Closed-network deployment (ADR 016) — no password,
// no real auth, the email is the identity.

import { Form, Input, Modal, Typography } from "antd";
import { useState } from "react";
import { setStoredEmail } from "../api/client";

interface EmailGateProps {
  onSubmit: (email: string) => void;
}

export function EmailGate({ onSubmit }: EmailGateProps) {
  const [form] = Form.useForm<{ email: string }>();
  const [submitting, setSubmitting] = useState(false);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const email = values.email.trim();
      setStoredEmail(email);
      onSubmit(email);
    } catch {
      // validateFields displays its own errors; nothing else to do here.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open
      title="Welcome to Lumina Capital"
      okText="Continue"
      cancelButtonProps={{ style: { display: "none" } }}
      closable={false}
      maskClosable={false}
      keyboard={false}
      onOk={handleOk}
      confirmLoading={submitting}
    >
      <Typography.Paragraph type="secondary">
        Enter your corporate email to begin. Your selection of the most-recently-viewed
        upload is restored automatically on any device you sign in from with the same
        address.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" onFinish={handleOk}>
        <Form.Item
          name="email"
          label="Corporate email"
          rules={[
            { required: true, message: "Email is required" },
            { type: "email", message: "Enter a valid email address" },
          ]}
        >
          <Input
            placeholder="alice@lumina.example"
            autoComplete="email"
            autoFocus
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
