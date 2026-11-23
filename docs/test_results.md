# sprint 2 test evidence

**task:** #16 - integration tests  
**branch:** task-16-integration-tests  
**date:** __________  

## tests run

command: `python -m pytest tests -q`

- passed: ______
- failed: ______
- skipped: ______
- screenshot: ______

command: `python -m pytest tests/test_sprint2_notifications_integration.py -q`

- passed: ______
- failed: ______
- screenshot: ______

## what i tested

- valid and invalid application status changes
- employer permissions
- application status history
- listing approval and resubmission
- application and listing notifications
- duplicate notification checks
- rollback when saving a notification fails

## coverage

coverage command (only if pytest-cov is installed): `python -m pytest tests --cov=app --cov-report=term-missing`

coverage result: ______ or not measured

## github evidence

- task #14 pr: ______
- task #16 pr: ______
- reviewer: ______
- merge status: ______

## any problems left

______
