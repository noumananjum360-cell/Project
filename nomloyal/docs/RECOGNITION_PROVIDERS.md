# Recognition providers (optional)

NomLoyal ships **no** face-recognition engine and **never** presents simulated recognition as real.
`app/integrations/recognition.py` defines the interface a real provider must implement:
`available()`, `enroll(customer_id, frames)`, `match(frame) -> [Match]`, `delete(customer_id)`.

Requirements for any provider before it may be registered in `PROVIDERS`:
- Works locally or under a documented data-processing agreement; tested on the store's cameras.
- Enrolment only for customers with a current **biometric** consent record; withdrawal deletes the enrolment.
- Never identifies or stores unknown people; does not store raw face images; templates stay in the provider's
  protected storage and are never logged.
- Matches below the confidence threshold are ignored; with confirmation on, staff confirm before anything is recorded.
- Matching/enrolment/deletion are written to the audit log.
- Validated on site (lighting, angle, resolution, masks/veils, distance). Report the measured accuracy honestly.
- The non-biometric lookup (QR / loyalty ID / phone) remains fully available.

Until such a provider exists the Camera page shows recognition as *Not available*, the consent screen refuses
biometric consent, and only labelled demo alerts can be created for training.
