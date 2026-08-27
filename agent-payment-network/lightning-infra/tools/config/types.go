package config

type NodeConfig struct {
	Alias        string `json:"alias"`
	Pubkey       string `json:"pubkey"`
	P2PAddress   string `json:"p2p_address"`
	GRPCEndpoint string `json:"grpc_endpoint"`
	RESTEndpoint string `json:"rest_endpoint"`
	MacaroonHex  string `json:"macaroon_hex"`
	TLSCertPath  string `json:"tls_cert_path"`
}

type ChannelParams struct {
	FundingAmountSats int64 `json:"funding_amount_sats"`
	PushSatoshis      int64 `json:"push_satoshis"`
	TargetConf        int   `json:"target_conf"`
}

type GuardrailParams struct {
	MaxPaymentSats int64 `json:"max_payment_sats"`
}

type TestData struct {
	User1Node         NodeConfig      `json:"user1_node"`
	User2Node         NodeConfig      `json:"user2_node"`
	TestChannelParams ChannelParams   `json:"test_channel_params"`
	GuardrailParams   GuardrailParams `json:"guardrail_params"`
}

