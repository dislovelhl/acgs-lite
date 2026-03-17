"""
ACGS-2 Enhanced Agent Bus - Verification Package
Constitutional Hash: cdd01ef066bc6cf2

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
