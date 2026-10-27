# Marketplace validation and inference instances

Use this reference during Phase 11. The goal is to stop treating a model's eventual serving hardware and the Marketplace compliance-validation hardware as one decision.

## Three separate contracts

| Field | What it controls | Evidence required |
|---|---|---|
| `SupportedRealtimeInferenceInstanceTypes` | Instance types a buyer may use to host the model on a Real-Time endpoint | The image and model artifact start, become healthy, and serve representative requests on each listed type |
| `SupportedTransformInstanceTypes` | Instance types a buyer may use for Batch Transform | The image and model artifact process representative batch input on each listed type |
| `ValidationSpecification...TransformResources.InstanceType` | The instance used by SageMaker's Batch Transform job to validate this model-package version | The instance is currently supported for Batch Transform in the submission region and can run the same image and model artifact |

Do not copy one list into another without test evidence. Marketplace model-package validation is a Batch Transform job even when the product is intended mainly for Real-Time inference.

The validation resource may be different from the eventual serving family. This is defensible only when the exact submitted image and model artifact can load and process representative input on both configurations. Passing validation on an older GPU proves the container contract on that validation resource. It does not prove latency, throughput, numerical behaviour, or accelerator-specific features on the serving family.

## Select the validation resource

1. Record the serving requirement: minimum accelerator memory, accelerator architecture or precision feature, container CUDA major version, and intended region.
2. Check the current [SageMaker GPU driver and instance-family table](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-gpu-drivers.html). Read the **Batch** rows for the validation job, not the Real-time rows.
3. Find a Batch-supported instance that meets the model's memory and architecture requirements.
4. Run the same image and model artifact on that Batch Transform configuration with representative input.
5. Add it to `SupportedTransformInstanceTypes` only if buyers may also use that type for Batch Transform and the seller is prepared to support it.
6. Record the evidence. Do not describe the model as validated on an untested serving family.

Prefer the smallest compatible Batch instance for the compliance run when several tested choices exist. Cost is secondary to architectural compatibility. A model that requires a GPU feature absent from every current Batch family has no supported validation resource.

## Driver and AMI compatibility

SageMaker publishes different default GPU drivers for Real-Time, Async, and Batch inference. For a Batch Transform validation job, use `TransformAmiVersion` only when the current driver table documents a compatible override for the selected family. SageMaker does not apply an override automatically.

An AMI override changes the managed host driver. It does not add a GPU architecture, memory capacity, or instance family that Batch Transform does not support.

## Classify the blocker

| Classification | Evidence | Next action |
|---|---|---|
| Unsupported | The instance family is absent from the current Batch rows, or the available GPU architecture cannot run the model | Test a genuinely compatible Batch fallback. If none exists, stop and report the service-support gap |
| Quota | The family is supported, but the account's regional quota is below the requested instance count | Request the relevant SageMaker Batch Transform quota increase |
| Capacity | The family is supported and quota is sufficient, but SageMaker cannot place the job | Retry later or test another supported family or region that the model and listing plan permit |
| Container compatibility | The job starts but the container fails to load, become healthy, or process the sample | Fix the image, model artifact, driver compatibility, or request contract; then rerun |

Do not prescribe quota requests for unsupported families. Do not describe transient capacity as a compliance failure until support and quota are confirmed.

## Submission record

Capture this before calling `CreateModelPackage`:

```
Serving contract:    <tested Real-Time instance types>
Batch contract:      <tested Batch Transform instance types>
Validation resource: <one Batch-supported instance type>
Driver / AMI:        <default, or documented TransformAmiVersion>
Region:              <CreateModelPackage region>
Evidence:            <test runs for each listed configuration>
```

## Sources

- [SageMaker GPU drivers and supported instance families](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-gpu-drivers.html)
- [CreateModelPackage API](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_CreateModelPackage.html)
- [ModelPackageValidationSpecification API](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_ModelPackageValidationSpecification.html)
- [TransformResources API](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_TransformResources.html)
- [Amazon SageMaker AI endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/sagemaker.html)
