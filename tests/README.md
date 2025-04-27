# GE Spot Test Structure

This directory contains the test suite for the GE Spot project. The tests are organized into different categories based on their purpose and behavior.

## Testing Philosophy

GE-Spot's testing approach is guided by these core principles:

1. **Reliability Validation**: Tests are designed to verify that the integration provides reliable electricity price data even when primary data sources fail.

2. **Global Coverage**: The test suite validates operation across all supported regions, ensuring consistent behavior regardless of market-specific differences.

3. **Timezone Correctness**: Special attention is paid to testing timezone handling and DST transitions, which are critical for ensuring accurate hourly prices.

4. **Graceful Failure Handling**: Tests deliberately introduce failures to verify the fallback system works as expected, ensuring users always get the best available data.

5. **Real-world Scenarios**: Test cases are derived from actual user scenarios and real market conditions to ensure practical functionality.

6. **Regression Prevention**: Any fixed bugs automatically get regression tests to prevent the same issues from recurring.

7. **Comprehensive Coverage**: The test suite aims to cover all components and their interactions, with special focus on critical paths like API clients and price processing.

8. **Modularity**: Tests are organized to support the modular architecture, making it easy to add tests for new regions or data sources.

## Directory Structure

```
tests/
├── conftest.py              # Test configuration and fixtures
├── README.md                # Testing documentation
├── lib/                     # Test library and utilities
│   ├── data/                # Test data and fixtures
│   ├── fixtures/            # Reusable test fixtures
│   └── mocks/               # Mock objects for testing
├── manual/                  # Manual test scripts
│   ├── api/                 # API-specific manual tests
│   └── integration/         # Integration manual tests
└── pytest/                  # Automated pytest tests
    ├── integration/         # Integration tests
    ├── lib/                 # Library unit tests
    └── unit/                # Component unit tests

## Test Categories

The test suite is organized into several categories:

1. **Unit Tests**: Testing individual components in isolation
   - API client tests
   - Parser tests
   - Utility function tests
   - Timezone handling tests

2. **Integration Tests**: Testing how components work together
   - End-to-end data flow tests
   - Configuration flow tests
   - Sensor state tests

3. **Functional Tests**: Testing real-world functionality
   - API source switching tests
   - Fallback mechanism tests 
   - Currency conversion tests

4. **Regression Tests**: Ensuring fixed bugs stay fixed

5. **Manual Tests**: Scripts for testing against live APIs
   - API-specific manual tests
   - Full chain integration tests

## Running Tests

### Unit Tests with pytest

To run all pytest unit tests:
```bash
pytest tests/pytest/unit/
```

To run a specific test category:
```bash
pytest custom_components/ge_spot/tests/api
pytest custom_components/ge_spot/tests/timezone
```

### Integration Tests

Run all integration tests:
```bash
pytest tests/pytest/integration/
pytest custom_components/ge_spot/tests/integration/
```

### Manual Tests

Run all manual tests using the master script:
```bash
./scripts/run_manual_tests.sh
```

Run a specific manual test:
```bash
python -m tests.python3.api.entsoe_test SE3
```

## Test Coverage Goals

The test suite aims for high coverage of critical paths:

- API clients and parsers: >90% coverage
- Coordinator and data processing: >85% coverage
- Timezone handling: >90% coverage
- Configuration flow: >80% coverage

New features are required to include appropriate test coverage before merging.

## Continuous Integration

The repository includes GitHub Actions workflows for automated testing:

- Running the test suite on each pull request
- Validating code style and formatting
- Checking for breaking changes to public APIs

## Writing New Tests

When adding new functionality to GE-Spot, follow these guidelines for test creation:

1. **Unit Tests**: Create tests for all new classes and functions
2. **Integration Tests**: Add tests for interactions with existing components
3. **Test Data**: Add relevant test fixtures to the appropriate directories
4. **Manual Tests**: If adding a new API source, create manual tests for validation

Use the existing test structure as a template when adding new tests to maintain consistency across the test suite.