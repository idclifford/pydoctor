"""
Render types from L{docutils.nodes.document} objects. 

This module provides yet another L{ParsedDocstring} subclass.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple, Union, cast

from pydoctor.epydoc.markup import DocstringLinker, ParseError, ParsedDocstring, get_parser_by_name
from pydoctor.node2stan import node2stan
from pydoctor.napoleon.docstring import TokenType, TypeDocstring

from docutils import nodes
from twisted.web.template import Tag, tags

class ParsedTypeDocstring(TypeDocstring, ParsedDocstring):
    """
    Add L{ParsedDocstring} interface on top of L{TypeDocstring} and 
    allow to parse types from L{nodes.Node} objects, providing the C{--process-types} option.
    """

    FIELDS = ('type', 'rtype', 'ytype', 'returntype', 'yieldtype')
    
    #                                                   yes this overrides the superclass type!
    _tokens: list[tuple[str | nodes.Node, TokenType]] # type: ignore

    def __init__(self, annotation: Union[nodes.document, str],
                 warns_on_unknown_tokens: bool = False, lineno: int = 0) -> None:
        ParsedDocstring.__init__(self, ())
        if isinstance(annotation, nodes.document):
            TypeDocstring.__init__(self, '', warns_on_unknown_tokens)

            _tokens = self._tokenize_node_type_spec(annotation)
            self._tokens = cast('list[tuple[str | nodes.Node, TokenType]]', 
                                self._build_tokens(_tokens))
            self._trigger_warnings()
        else:
            TypeDocstring.__init__(self, annotation, warns_on_unknown_tokens)
        
        
        # We need to store the line number because we need to pass it to DocstringLinker.link_xref
        self._lineno = lineno

    @property
    def has_body(self) -> bool:
        return len(self._tokens)>0

    def to_node(self) -> nodes.document:
        """
        Not implemented at this time :/
        """
        #TODO: Fix this soon - PR https://github.com/twisted/pydoctor/pull/874
        raise NotImplementedError()

    def to_stan(self, docstring_linker: DocstringLinker) -> Tag:
        """
        Present the type as a stan tree. 
        """
        return self._convert_type_spec_to_stan(docstring_linker)

    def _tokenize_node_type_spec(self, spec: nodes.document) -> List[Union[str, nodes.Node]]:
        def _warn_not_supported(n:nodes.Node) -> None:
            self.warnings.append(f"Unexpected element in type specification field: element '{n.__class__.__name__}'. "
                                    "This value should only contain text or inline markup.")

        tokens: List[Union[str, nodes.Node]] = []
        # Determine if the content is nested inside a paragraph
        # this is generally the case, except for consolidated fields generate documents.
        if spec.children and isinstance(spec.children[0], nodes.paragraph):
            if len(spec.children)>1:
                _warn_not_supported(spec.children[1])
            children = spec.children[0].children
        else:
            children = spec.children
        
        for child in children:
            if isinstance(child, nodes.Text):
                # Tokenize the Text node with the same method TypeDocstring uses.
                tokens.extend(TypeDocstring._tokenize_type_spec(child.astext()))
            elif isinstance(child, nodes.Inline):
                tokens.append(child)
            else:
                _warn_not_supported(child)
        
        return tokens

    def _convert_obj_tokens_to_stan(self, tokens: List[Tuple[Any, TokenType]], 
                                    docstring_linker: DocstringLinker) -> list[tuple[Any, TokenType]]:
        """
        Convert L{TokenType.OBJ} and PEP 484 like L{TokenType.DELIMITER} type to stan, merge them together. Leave the rest untouched. 

        @param tokens: List of tuples: C{(token, type)}
        """

        combined_tokens: list[tuple[Any, TokenType]] = []

        open_parenthesis = 0
        open_square_braces = 0

        for _token, _type in tokens:
            # The actual type of_token is str | Tag | Node. 

            if (_type is TokenType.DELIMITER and _token in ('[', '(', ')', ']')) \
               or _type is TokenType.OBJ: 
                if _token == "[": open_square_braces += 1
                elif _token == "(": open_parenthesis += 1

                if _type is TokenType.OBJ:
                    _token = docstring_linker.link_xref(
                                _token, _token, self._lineno)

                if open_square_braces + open_parenthesis > 0:
                    try: last_processed_token = combined_tokens[-1]
                    except IndexError:
                        combined_tokens.append((_token, _type))
                    else:
                        if last_processed_token[1] is TokenType.OBJ \
                           and isinstance(last_processed_token[0], Tag):
                            # Merge with last Tag
                            if _type is TokenType.OBJ:
                                assert isinstance(_token, Tag)
                                last_processed_token[0](*_token.children)
                            else:
                                last_processed_token[0](_token)
                        else:
                            combined_tokens.append((_token, _type))
                else:
                    combined_tokens.append((_token, _type))
                
                if _token == "]": open_square_braces -= 1
                elif _token == ")": open_parenthesis -= 1

            else:
                # the token will be processed in _convert_type_spec_to_stan() method.
                combined_tokens.append((_token, _type))

        return combined_tokens

    def _convert_type_spec_to_stan(self, docstring_linker: DocstringLinker) -> Tag:
        """
        Convert type to L{Tag} object.
        """

        tokens = self._convert_obj_tokens_to_stan(self._tokens, docstring_linker)

        warnings: List[ParseError] = []

        converters: Dict[TokenType, Callable[[Union[str, Tag]], Union[str, Tag]]] = {
            TokenType.LITERAL:      lambda _token: tags.span(_token, class_="literal"),
            TokenType.CONTROL:      lambda _token: tags.em(_token),
            # We don't use safe_to_stan() here, if these converter functions raise an exception, 
            # the whole type docstring will be rendered as plaintext.
            # it does not crash on invalid xml entities
            TokenType.REFERENCE:    lambda _token: get_parser_by_name('restructuredtext')(_token, warnings).to_stan(docstring_linker) if isinstance(_token, str) else _token, 
            TokenType.UNKNOWN:      lambda _token: get_parser_by_name('restructuredtext')(_token, warnings).to_stan(docstring_linker) if isinstance(_token, str) else _token, 
            TokenType.OBJ:          lambda _token: _token, # These convertions (OBJ and DELIMITER) are done in _convert_obj_tokens_to_stan().
            TokenType.DELIMITER:    lambda _token: _token, 
            TokenType.ANY:          lambda _token: _token, 
        }

        for w in warnings:
            self.warnings.append(w.descr())

        converted = Tag('')

        for token, type_ in tokens:
            assert token is not None
            if isinstance(token, nodes.Node):
                token = node2stan(token, docstring_linker)
            assert isinstance(token, (str, Tag))
            converted_token = converters[type_](token)
            converted(converted_token)

        return converted
