Test 1
TestExact

org.apache.catalina.ant

# ---------------- Python Style ----------------
# This line is a Python comment and should be ignored
import os  # This inline comment should be removed
print("Hello World")  # Keyword test should ignore comment
keyword_in_code = "apache"  # Should match 'apache' in code

# ---------------- Java / C++ / JS Style ----------------
// This is a single line comment in Java/C++/JS
int x = 10; // Inline comment after code
String s = "org.apache.catalina.ant"; // Keyword in string, inline comment ignored
/* This is a block comment
   spanning multiple lines
   keyword inside block should be ignored: org.apache.catalina.ant
*/

# ---------------- Shell / Bash Style ----------------
# This is a shell comment
echo "keyword org.apache in code"  # Inline shell comment

# ---------------- SQL Style ----------------
-- This is a SQL comment
SELECT * FROM users; -- Inline comment with keyword
/* Multi-line SQL comment
   keyword org.apache.catalina.ant inside
*/

# ---------------- HTML / XML / JSP Style ----------------
<!-- This is an HTML comment -->
<div>keyword apache in div</div>
<!--
   Multi-line HTML comment
   org.apache.catalina.ant inside
-->

# ---------------- Assembly Style ----------------
mov eax, ebx ; This is a comment in assembly, keyword inside ignored
; Full line comment in asm
add eax, 1

# ---------------- Edge Cases ----------------
abc/def/apache.txt  # Path-like line should still match keyword
"path/with/keyword/org.apache"  # Should match
"// Not a comment if inside quotes"  # Should match
"# Also inside quotes should match"  # Should match
