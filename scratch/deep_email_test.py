import smtplib
import dns.resolver
import socket

def check_email_exists(email):
    domain = email.split('@')[-1]
    try:
        # Get MX record
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(records[0].exchange)
        
        # Connect to server
        server = smtplib.SMTP(timeout=5)
        server.set_debuglevel(1)
        server.connect(mx_record)
        server.helo(socket.gethostname())
        server.mail('me@test.com')
        code, message = server.rcpt(email)
        server.quit()
        
        if code == 250:
            return True, f"Possible (Code {code})"
        else:
            return False, f"Rejected (Code {code}: {message})"
            
    except Exception as e:
        return False, str(e)

# Test cases
print("Testing REAL address (dhavanvemulapalli@gmail.com):")
print(check_email_exists("dhavanvemulapalli@gmail.com"))

print("\nTesting FAKE address (thisemaildefinitelydoesnotexist12345@gmail.com):")
print(check_email_exists("thisemaildefinitelydoesnotexist12345@gmail.com"))
