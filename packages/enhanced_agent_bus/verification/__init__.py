"""
ACGS-2 Enhanced Agent Bus - Verification Package
Constitutional Hash: 608508a9bd224290

.. note::
    New verification code should be added to ``verification_layer/`` instead.
    This package is maintained for backwards compatibility with existing
    consumers (breakthrough/, tests/breakthrough/, workflows/).

Submodules:
    - maci_verification: ConstitutionalVerificationPipeline (MACI role separation)
    - maci_pipeline: MACIVerificationPipeline (governance decision verification)
    - saga_transaction: SagaTransaction (compensable LLM workflows)
    - sagallm_transactions: SagaLLMTransactionManager
    - z3_adapter: ConstitutionalZ3Verifier
"""
