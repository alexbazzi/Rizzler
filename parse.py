import sys
from lex import *
from emit import *

# Parser object keeps track of current token and checks 
# if the code matches the grammar.
class Parser:
    def __init__(self, lexer, emitter):
        self.lexer = lexer
        self.emitter = emitter

        self.symbols = set()        # Variables declared so far.
        self.labelsDeclared = set() # Labels declared so far.
        self.labelsGotoed = set()   # Labels goto'ed so far.

        self.curToken = None
        self.peekToken = None
        self.nextToken()
        self.nextToken()

    # Return True if the current token matches
    def checkToken(self, kind):
        return kind == self.curToken.kind

    # Return True if the next token matches
    def checkPeek(self, kind):
        return kind == self.peekToken.kind

    # Try to match current token. If not, error. Advance either way.
    def match(self, kind):
        if not self.checkToken(kind):
            self.abort("Expected " + kind.name + ", got " + self.curToken.kind.name)
        self.nextToken()
    
    # Advance the current token
    def nextToken(self):
        self.curToken = self.peekToken
        self.peekToken = self.lexer.getToken()
        # No need to pass EOF, lexer handles that.
    
    def abort(self, message):
        sys.exit("[Error] " + message)
    
    def isComparisonOperator(self):
        return self.checkToken(TokenType.GT) \
                or self.checkToken(TokenType.GTEQ) \
                or self.checkToken(TokenType.LT) \
                or self.checkToken(TokenType.LTEQ) \
                or self.checkToken(TokenType.EQEQ) \
                or self.checkToken(TokenType.NOTEQ) 

    # Production rules

    # program ::= {statement}
    def program(self):
        self.emitter.headerLine("#include <stdio.h>")
        self.emitter.headerLine("int main(void) {")

        # Skip excess newlines.
        while self.checkToken(TokenType.NEWLINE):
            self.nextToken()

        # Parse all the statements in the program.
        while not self.checkToken(TokenType.EOF):
            self.statement()
        
        # End of file cleanup
        self.emitter.emitLine("return 0;")
        self.emitter.emitLine("}")

        
        # Check that each label referenced in a GOTO is declared.
        for label in self.labelsGotoed:
            if label not in self.labelsDeclared:
                self.abort("Attempting to GOTO to undeclared label: " + label)
    
    def statement(self):
        # Check the first token to determine the type of statement

        if self.checkToken(TokenType.YAP):
            self.nextToken()

            if self.checkToken(TokenType.STRING):
                self.emitter.emitLine("printf(\"" + self.curToken.text + "\\n\");")
                self.nextToken() # Expect a string literal
            else:
                self.emitter.emit("printf(\"%" + ".2f\\n\"" + ", (float)(")
                self.expression()
                self.emitter.emitLine("));")

        # "IF" comparison "THEN" {statement} "ENDIF"
        elif self.checkToken(TokenType.IF):
            self.nextToken()
            self.emitter.emit("if(")
            self.comparison()

            self.match(TokenType.THEN)
            self.nl()
            self.emitter.emitLine(") {")

            # Zero or more statements in the body.
            while not self.checkToken(TokenType.ENDIF):
                self.statement()

            self.match(TokenType.ENDIF)
            self.emitter.emitLine("}")

        # "COOKING" comparison "RUNITBACK" nl {statement nl} "COOKED" nl
        elif self.checkToken(TokenType.COOKING):
            self.nextToken()
            self.emitter.emit("while(")
            self.comparison()

            self.match(TokenType.RUNITBACK)
            self.nl()
            self.emitter.emitLine(") {")

            # Zero or more statements in the loop body
            while not self.checkToken(TokenType.COOKED):
                self.statement()

            self.match(TokenType.COOKED)
            self.emitter.emitLine("}")

        # "LABEL" ident
        elif self.checkToken(TokenType.LABEL):
            self.nextToken()

            # Ensure label doesn't exist already.
            if self.curToken.text in self.labelsDeclared:
                self.abort("Label already exists: " + self.curToken.text)
            self.labelsDeclared.add(self.curToken.text)

            self.emitter.emitLine(self.curToken.text + ":")
            self.match(TokenType.IDENT)

        # "GOTO" ident 
        elif self.checkToken(TokenType.GOTO):
            self.nextToken()
            self.labelsGotoed.add(self.curToken.text)
            self.emitter.emitLine("goto" + self.curToken.text + ";")
            self.match(TokenType.IDENT)

        # "NOCAP" ident "=" expression
        elif self.checkToken(TokenType.NOCAP):
            self.nextToken()
            
            # Check if ident exists in symbol table. If not, declare it.
            if self.curToken.text not in self.symbols:
                self.symbols.add(self.curToken.text)
                self.emitter.headerLine("float " + self.curToken.text + ";")

            self.emitter.emit(self.curToken.text + " = ")
            self.match(TokenType.IDENT)
            self.match(TokenType.EQ)

            self.expression()
            self.emitter.emitLine(";");

        # "PREACH" ident
        elif self.checkToken(TokenType.PREACH):
            self.nextToken()

            # Check if variable exists. If not, declare it.
            if self.curToken.text not in self.symbols:
                self.symbols.add(self.curToken.text)
                self.emitter.headerLine("float " + self.curToken.text + ";")

            # Emit scanf and validate the input
            self.emitter.emitLine("if(0 == scanf(\"%" + "f\", &" + self.curToken.text + ")) {")
            self.emitter.emitLine(self.curToken.text + " = 0;")
            self.emitter.emit("scanf(\"%")
            self.emitter.emitLine("*s\");")
            self.emitter.emitLine("}")
            self.match(TokenType.IDENT)

        else:
            self.abort("Invalid statement at " 
                       + self.curToken.text + " (" 
                       + self.curToken.kind.name + ")")

        self.nl() # Newline
    
    # comparison ::= expression (("==" | "!=" | ">" | ">=" | "<" | "<=") expression)+
    def comparison(self):
        self.expression()

        # Must be at least one comparison operators and another expression.
        if self.isComparisonOperator():
            self.emitter.emit(self.curToken.text)
            self.nextToken()
            self.expression()
        else:
            self.abort("Expected comparison operator at: " + self.curToken.text)

        # Can have zero or more comparison operators and expressions.
        while self.isComparisonOperator():
            self.emitter.emit(self.curToken.text)
            self.nextToken()
            self.expression()
        

    # expression ::= term {( "-" | "+") term}
    def expression(self):
        self.term()

        # Can have zero or more +/- and expressions.
        while self.checkToken(TokenType.PLUS) or self.checkToken(TokenType.MINUS):
            self.emitter.emit(self.curToken.text)
            self.nextToken()
            self.term()
    
    # term ::= unary {( "/" | "*") unary}
    def term(self):
        self.unary()

        # Can have zero or more *// and expressions.
        while self.checkToken(TokenType.ASTERISK) or self.checkToken(TokenType.SLASH):
            self.emitter.emit(self.curToken.text)
            self.nextToken()
            self.unary()

    # unary ::= ["+" | "-"] primary
    def unary(self):
        # Optional unary +/-
        if self.checkToken(TokenType.PLUS) or self.checkToken(TokenType.MINUS):
            self.emitter.emit(self.curToken.text)
            self.nextToken()
        self.primary()

    # primary ::= number | ident
    def primary(self):
        if self.checkToken(TokenType.NUMBER):
            self.emitter.emit(self.curToken.text)
            self.nextToken()
        elif self.checkToken(TokenType.IDENT):
            # Ensure the variable exists.
            if self.curToken.text not in self.symbols:
                self.abort("Referencing variable before assignment: " + self.curToken.text)

            self.emitter.emit(self.curToken.text)
            self.nextToken()
        else:
            self.abort("Unpexpected token at " + self.curToken.text)

    
    # nl ::= '\n'+
    def nl(self):
        # Require at least one newline.
        self.match(TokenType.NEWLINE)

        # Also allow extra lines.
        while self.checkToken(TokenType.NEWLINE):
            self.nextToken()