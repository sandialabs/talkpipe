# Security Policy

## Supported Versions

We actively support security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in TalkPipe, please report it responsibly:

### Private Disclosure

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security reports to: tlbauer@sandia.gov
3. Include the following information:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact
   - Suggested fix (if available)

### What to Expect

- **Response Time**: We aim to acknowledge receipt within 2 business days
- **Initial Assessment**: Initial security assessment within 5 business days
- **Updates**: We will provide updates on our progress every 7 days until resolution
- **Disclosure**: After the vulnerability is fixed, we will coordinate public disclosure

### Security Best Practices

When using TalkPipe:

1. **Keep Dependencies Updated**: Regularly update TalkPipe and its dependencies
2. **Secure Configuration**: Follow security best practices for API keys and configuration
3. **Container Security**: When using Docker, ensure base images are up to date
4. **Network Security**: Implement appropriate network security measures
5. **Access Control**: Limit access to TalkPipe deployments to authorized users only

### Security Features

TalkPipe includes several security measures:

- Dependency scanning via Safety and Bandit
- Container vulnerability scanning with Trivy  
- Static code analysis with CodeQL
- Automated dependency updates via Dependabot
- Non-root container execution
- Input validation and sanitization

### Acknowledgments

We appreciate security researchers who responsibly disclose vulnerabilities. Contributors will be acknowledged (unless they prefer to remain anonymous) in our security advisories and release notes.