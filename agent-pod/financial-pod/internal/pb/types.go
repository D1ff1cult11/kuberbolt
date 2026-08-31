// Package pb contains hand-written Go types matching the proto definitions in
// agent-pod/proto/agent_service.proto. These replace protoc-generated code
// until a proper codegen step is added to the build.
//
// All message types implement proto.Message via google.golang.org/protobuf.
package pb

// FinancialPodService — Provider Role: manage incoming L402-gated requests.

type CreateHoldInvoiceRequest struct {
	AmountMSat uint64 `json:"amount_msat"`
	Memo       string `json:"memo"`
}

type CreateHoldInvoiceResponse struct {
	HoldInvoice string `json:"hold_invoice"`
	PaymentHash string `json:"payment_hash"` // hex
	// Preimage is kept inside the FP; NEVER sent over the wire.
}

type ValidateHoldRequest struct {
	PaymentHash string `json:"payment_hash"` // hex
}

type ValidateHoldResponse struct {
	IsLocked  bool   `json:"is_locked"`
	AmountMSat uint64 `json:"amount_msat"`
}

// FinancialPodService — Client Role: pay outbound invoices.

type PayHoldInvoiceRequest struct {
	Invoice string `json:"invoice"`
}

type PayHoldInvoiceResponse struct {
	Success  bool   `json:"success"`
	Status   string `json:"status"`   // "pending", "settled", "failed"
	Preimage string `json:"preimage"` // hex — populated on success
}

type SettleHoldInvoiceRequest struct {
	Preimage string `json:"preimage"` // hex
}

type SettleHoldInvoiceResponse struct {
	Success bool `json:"success"`
}

// CommonSDKService — CallService is the primary compute-for-payment RPC.

type CallServiceRequest struct {
	ServiceKind string `json:"service_kind"`
	JobSpec     []byte `json:"job_spec"`      // JSON-encoded job definition
	MacaroonHex string `json:"macaroon_hex"`  // present on authenticated retry
	PreimageHex string `json:"preimage_hex"`  // present on authenticated retry
}

type CallServiceResponse struct {
	OutputData []byte `json:"output_data"`
	Status     string `json:"status"`
	JobID      string `json:"job_id"`
}

// PaymentRequired is returned in gRPC status details when L402 challenge is issued.
type PaymentRequired struct {
	Invoice     string `json:"invoice"`
	MacaroonHex string `json:"macaroon_hex"`
	PaymentHash string `json:"payment_hash"` // hex
	AmountMSat  int64  `json:"amount_msat"`
	ExpirySec   int32  `json:"expiry_sec"`
}

// Budget info types.

type GetBudgetInfoRequest struct{}

type GetBudgetInfoResponse struct {
	DailyLimitMSat   int64 `json:"daily_limit_msat"`
	DailySpentMSat   int64 `json:"daily_spent_msat"`
	MonthlyLimitMSat int64 `json:"monthly_limit_msat"`
	MonthlySpentMSat int64 `json:"monthly_spent_msat"`
	AvailableMSat    int64 `json:"available_msat"`
}

// Channel info types.

type ChannelInfo struct {
	PeerPubkey       string `json:"peer_pubkey"`
	CapacityMSat     int64  `json:"capacity_msat"`
	LocalBalanceMSat int64  `json:"local_balance_msat"`
	RemoteBalanceMSat int64 `json:"remote_balance_msat"`
	Active           bool   `json:"active"`
}

type GetChannelInfoRequest struct{}

type GetChannelInfoResponse struct {
	Channels []*ChannelInfo `json:"channels"`
}

// TxStatus types.

type TxStatusRequest struct {
	TxID string `json:"tx_id"`
}

type TxStatusResponse struct {
	Status     string `json:"status"`
	AmountMSat int64  `json:"amount_msat"`
	Timestamp  int64  `json:"timestamp"`
}
