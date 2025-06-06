"""Classes that generate the summary pages."""
from __future__ import annotations

from collections import defaultdict
from string import Template
from textwrap import dedent
from typing import (
    TYPE_CHECKING, DefaultDict, Dict, Iterable, List, Mapping, MutableSet,
    Sequence, Tuple, Type, Union, cast
)

from twisted.web.template import Element, Tag, TagLoader, renderer, tags

from pydoctor import epydoc2stan, model, linker
from pydoctor.templatewriter import TemplateLookup, util
from pydoctor.templatewriter.pages import Page

if TYPE_CHECKING:
    from twisted.web.template import Flattenable


def moduleSummary(module: model.Module, page_url: str) -> Tag:
    r: Tag = tags.li(
        tags.code(linker.taglink(module, page_url, label=module.name)), ' - ',
        epydoc2stan.format_summary(module)
        )
    if module.isPrivate:
        r(class_='private')
    if not isinstance(module, model.Package):
        return r
    contents = list(module.submodules())
    if not contents:
        return r

    ul = tags.ul()

    if len(contents) > 50 and not any(any(s.submodules()) for s in contents):
        # If there are more than 50 modules and no submodule has
        # further submodules we use a more compact presentation.
        li = tags.li(class_='compact-modules')
        for m in sorted(contents, key=util.alphabetical_order_func):
            span = tags.span()
            span(tags.code(linker.taglink(m, m.url, label=m.name)))
            span(', ')
            if m.isPrivate:
                span(class_='private')
            li(span)
        # remove the last trailing comma
        li.children[-1].children.pop() # type: ignore
        ul(li)
    else:
        for m in sorted(contents, key=util.alphabetical_order_func):
            ul(moduleSummary(m, page_url))
    r(ul)
    return r

def _lckey(x: model.Documentable) -> Tuple[str, str]:
    return (x.fullName().lower(), x.fullName())

class ModuleIndexPage(Page):

    filename = 'moduleIndex.html'

    def __init__(self, system: model.System, template_lookup: TemplateLookup):

        # Override L{Page.loader} because here the page L{filename}
        # does not equal the template filename.
        super().__init__(system=system, template_lookup=template_lookup,
            loader=template_lookup.get_loader('summary.html') )

    def title(self) -> str:
        return "Module Index"

    @renderer
    def stuff(self, request: object, tag: Tag) -> Tag:
        tag.clear()
        tag([moduleSummary(o, self.filename) for o in self.system.rootobjects])
        return tag

    @renderer
    def heading(self, request: object, tag: Tag) -> Tag:
        tag().clear()
        tag("Module Index")
        return tag

def findRootClasses(
        system: model.System
        ) -> Sequence[Tuple[str, Union[model.Class, Sequence[model.Class]]]]:
    roots: Dict[str, Union[model.Class, List[model.Class]]] = {}
    for cls in system.objectsOfType(model.Class):
        if ' ' in cls.name or not cls.isVisible:
            continue
        if cls.bases:
            for name, base in zip(cls.bases, cls.baseobjects):
                if base is None or not base.isVisible:
                    # The base object is in an external library or filtered out (not visible)
                    # Take special care to avoid AttributeError: 'Class' object has no attribute 'append'.
                    if isinstance(roots.get(name), model.Class):
                        roots[name] = [cast(model.Class, roots[name])]
                    cast(List[model.Class], roots.setdefault(name, [])).append(cls)
                elif base.system is not system:
                    # Edge case with multiple systems, is it even possible to run into this code?
                    roots[base.fullName()] = base
        else:
            # This is a common root class. 
            roots[cls.fullName()] = cls
    return sorted(roots.items(), key=lambda x:x[0].lower())

def isPrivate(obj: model.Documentable) -> bool:
    """Is the object itself private or does it live in a private context?"""

    while not obj.isPrivate:
        parent = obj.parent
        if parent is None:
            return False
        obj = parent

    return True

def isClassNodePrivate(cls: model.Class) -> bool:
    """Are a class and all its subclasses are private?"""

    if not isPrivate(cls):
        return False

    for sc in cls.subclasses:
        if not isClassNodePrivate(sc):
            return False

    return True

def subclassesFrom(
        hostsystem: model.System,
        cls: model.Class,
        anchors: MutableSet[str],
        page_url: str
        ) -> Tag:
    r: Tag = tags.li()
    if isClassNodePrivate(cls):
        r(class_='private')
    name = cls.fullName()
    if name not in anchors:
        r(tags.a(name=name))
        anchors.add(name)
    r(tags.div(tags.code(linker.taglink(cls, page_url)), ' - ',
      epydoc2stan.format_summary(cls)))
    scs = [sc for sc in cls.subclasses if sc.system is hostsystem and ' ' not in sc.fullName()
           and sc.isVisible]
    if len(scs) > 0:
        ul = tags.ul()
        for sc in sorted(scs, key=_lckey):
            ul(subclassesFrom(hostsystem, sc, anchors, page_url))
        r(ul)
    return r

class ClassIndexPage(Page):

    filename = 'classIndex.html'

    def __init__(self, system: model.System, template_lookup: TemplateLookup):

        # Override L{Page.loader} because here the page L{filename}
        # does not equal the template filename.
        super().__init__(system=system, template_lookup=template_lookup,
            loader=template_lookup.get_loader('summary.html') )

    def title(self) -> str:
        return "Class Hierarchy"

    @renderer
    def stuff(self, request: object, tag: Tag) -> Tag:
        t = tag
        anchors: MutableSet[str] = set()
        for b, o in findRootClasses(self.system):
            if isinstance(o, model.Class):
                t(subclassesFrom(self.system, o, anchors, self.filename))
            else:
                url = self.system.intersphinx.getLink(b)
                if url:
                    link:"Flattenable" = linker.intersphinx_link(b, url)
                else:
                    # TODO: we should find a way to use the pyval colorizer instead
                    # of manually creating the intersphinx link, this would allow to support
                    # linking to namedtuple(), proxyForInterface() and all other ast constructs.
                    # But the issue is that we're using the string form of base objects in order
                    # to compare and aggregate them, as a consequence we can't directly use the colorizer.
                    # Another side effect is that subclasses of collections.namedtuple() and namedtuple() 
                    # (depending on how the name is imported) will not be aggregated under the same list item :/
                    link = b
                item = tags.li(tags.code(link))
                
                if all(isClassNodePrivate(sc) for sc in o):
                    # This is an external class used only by private API;
                    # mark the whole node private.
                    item(class_='private')
                if o:
                    ul = tags.ul()
                    for sc in sorted(o, key=_lckey):
                        ul(subclassesFrom(self.system, sc, anchors, self.filename))
                    item(ul)
                t(item)
        return t

    @renderer
    def heading(self, request: object, tag: Tag) -> Tag:
        tag.clear()
        tag("Class Hierarchy")
        return tag


class LetterElement(Element):

    def __init__(self,
            loader: TagLoader,
            initials: Mapping[str, Sequence[model.Documentable]],
            letter: str
            ):
        super().__init__(loader=loader)
        self.initials = initials
        self.my_letter = letter

    @renderer
    def letter(self, request: object, tag: Tag) -> Tag:
        tag(self.my_letter)
        return tag

    @renderer
    def letterlinks(self, request: object, tag: Tag) -> Tag:
        letterlinks: List["Flattenable"] = []
        for initial in sorted(self.initials):
            if initial == self.my_letter:
                letterlinks.append(initial)
            else:
                letterlinks.append(tags.a(href='#'+initial)(initial))
            letterlinks.append(' - ')
        if letterlinks:
            del letterlinks[-1]
        tag(letterlinks)
        return tag

    @renderer
    def names(self, request: object, tag: Tag) -> "Flattenable":
        def link(obj: model.Documentable) -> Tag:
            # The "data-type" attribute helps doc2dash figure out what
            # category (class, method, etc.) an object belongs to.
            attributes = {}
            if obj.kind:
                attributes["data-type"] = epydoc2stan.format_kind(obj.kind)
            return tags.code(
                linker.taglink(obj, NameIndexPage.filename), **attributes
                )
        name2obs: DefaultDict[str, List[model.Documentable]] = defaultdict(list)
        for obj in self.initials[self.my_letter]:
            name2obs[obj.name].append(obj)
        r = []
        for name in sorted(name2obs, key=lambda x:(x.lower(), x)):
            item: Tag = tag.clone()(name)
            obs = name2obs[name]
            if all(isPrivate(ob) for ob in obs):
                item(class_='private')
            if len(obs) == 1:
                item(' - ', link(obs[0]))
            else:
                ul = tags.ul()
                for ob in sorted(obs, key=_lckey):
                    subitem = tags.li(link(ob))
                    if isPrivate(ob):
                        subitem(class_='private')
                    ul(subitem)
                item(ul)
            r.append(item)
        return r


class NameIndexPage(Page):

    filename = 'nameIndex.html'

    def __init__(self, system: model.System, template_lookup: TemplateLookup):
        super().__init__(system=system, template_lookup=template_lookup)
        self.initials: Dict[str, List[model.Documentable]] = {}
        for ob in self.system.allobjects.values():
            if ob.isVisible:
                self.initials.setdefault(ob.name[0].upper(), []).append(ob)


    def title(self) -> str:
        return "Index of Names"

    @renderer
    def heading(self, request: object, tag: Tag) -> Tag:
        return tag.clear()("Index of Names")

    @renderer
    def index(self, request: object, tag: Tag) -> "Flattenable":
        r = []
        for i in sorted(self.initials):
            r.append(LetterElement(TagLoader(tag), self.initials, i))
        return r


class IndexPage(Page):

    filename = 'index.html'

    def title(self) -> str:
        return f"API Documentation for {self.system.projectname}"

    @renderer
    def roots(self, request: object, tag: Tag) -> "Flattenable":
        r = []
        for o in self.system.rootobjects:
            r.append(tag.clone().fillSlots(root=tags.code(
                linker.taglink(o, self.filename)
                )))
        return r

    @renderer
    def rootkind(self, request: object, tag: Tag) -> Tag:
        rootkinds = sorted(set([o.kind for o in self.system.rootobjects]), key=lambda k:k.name)
        return tag.clear()('/'.join(
             epydoc2stan.format_kind(o, plural=True).lower()
             for o in rootkinds ))


def hasdocstring(ob: model.Documentable) -> bool:
    for source in ob.docsources():
        if source.docstring is not None:
            return True
    return False

class UndocumentedSummaryPage(Page):

    filename = 'undoccedSummary.html'

    def __init__(self, system: model.System, template_lookup: TemplateLookup):
        # Override L{Page.loader} because here the page L{filename}
        # does not equal the template filename.
        super().__init__(system=system, template_lookup=template_lookup,
            loader=template_lookup.get_loader('summary.html') )

    def title(self) -> str:
        return "Summary of Undocumented Objects"

    @renderer
    def heading(self, request: object, tag: Tag) -> Tag:
        return tag.clear()("Summary of Undocumented Objects")

    @renderer
    def stuff(self, request: object, tag: Tag) -> Tag:
        undoccedpublic = [o for o in self.system.allobjects.values()
                          if o.isVisible and not hasdocstring(o)]
        undoccedpublic.sort(key=lambda o:o.fullName())
        for o in undoccedpublic:
            kind = o.kind
            assert kind is not None  # 'kind is None' makes the object invisible
            tag(tags.li(
                epydoc2stan.format_kind(kind), " - ",
                tags.code(linker.taglink(o, self.filename))
                ))
        return tag

# TODO: The help page should dynamically include notes about the (source) code links. 
class HelpPage(Page):

    filename = 'apidocs-help.html'

    RST_SOURCE_TEMPLATE = Template('''
    Navigation
    ----------

    There is one page per class, module and package. 
    Each page present summary table(s) which feature the members of the object.

    Package or Module page
    ~~~~~~~~~~~~~~~~~~~~~~~

    Each of these pages has two main sections consisting of:

    - summary tables submodules and subpackages and the members of the module or in the ``__init__.py`` file. 
    - detailed descriptions of function and attribute members.

    Class page
    ~~~~~~~~~~

    Each class has its own separate page. 
    Each of these pages has three main sections consisting of:

    - declaration, constructors, know subclasses and description
    - summary tables of members, including inherited
    - detailed descriptions of method and attribute members
    
    Entries in each of these sections are omitted if they are empty or not applicable.

    Module Index
    ~~~~~~~~~~~~
    
    Provides a high level overview of the packages and modules structure.
    
    Class Hierarchy
    ~~~~~~~~~~~~~~~
    
    Provides a list of classes organized by inheritance structure. Note that ``object`` is ommited.

    Index Of Names
    ~~~~~~~~~~~~~~
    
    The Index contains an alphabetic index of all objects in the documentation.


    Search
    ------

    You can search for definitions of modules, packages, classes, functions, methods and attributes. 
    
    These items can be searched using part or all of the name and/or from their docstrings if "search in docstrings" is enabled. 
    Multiple search terms can be provided separated by whitespace. 

    The search is powered by `lunrjs <https://lunrjs.com/>`_.

    Indexing
    ~~~~~~~~
    
    By default the search only matches on the name of the object. 
    Enable the full text search in the docstrings with the checkbox option. 

    You can instruct the search to look only in specific fields by passing the field name in the search like ``docstring:term``. 
    
    **Possible fields are**: 
    
    - ``name``, the name of the object (example: "MyClassAdapter" or "my_fmin_opti").
    - ``qname``, the fully qualified name of the object (example: "lib.classses.MyClassAdapter").
    - ``names``, the name splitted on camel case or snake case (example: "My Class Adapter" or "my fmin opti")
    - ``docstring``, the docstring of the object (example: "This is an adapter for HTTP json requests that logs into a file...")
    - ``kind``, can be one of: $kind_names
        
    Last two fields are only applicable if "search in docstrings" is enabled. 

    Other search features
    ~~~~~~~~~~~~~~~~~~~~~

    Term presence. 
        The default behaviour is to give a better ranking to object matching multiple terms of your query,
        but still show entries that matches only one of the two terms. 
        To change this behavour, you can use the sign ``+``.
        
        - To indicate a term must exactly match use the plus sing: ``+``. 
        - To indicate a term must not match use the minus sing: ``-``.
        
    
    Wildcards
        A trailling wildcard is automatically added to each term of your query if they don't contain an explicit term presence (``+`` or ``-``). 
        Searching for ``foo`` is the same as searching for ``foo*``. 
        
        If the query include a dot (``.``), a leading wildcard will to also added, 
        searching for ``model.`` is the same as ``*model.*`` and ``.model`` is the same as ``*.model*``.

        In addition to this automatic feature, you can manually add a wildcard anywhere else in the query.


    Query examples
    ~~~~~~~~~~~~~~

    - "doc" matches "pydoctor.model.Documentable" and "pydoctor.model.DocLocation".
    - "+doc" matches "pydoctor.model.DocLocation" but won't match "pydoctor.model.Documentable".
    - "ensure doc" matches "pydoctor.epydoc2stan.ensure_parsed_docstring" and other object whose matches either "doc" or "ensure".
    - "inp str" matches "java.io.InputStream" and other object whose matches either "in" or "str".
    - "model." matches everything in the pydoctor.model module.
    - ".web.*tag" matches "twisted.web.teplate.Tag" and related.
    - "docstring:ansi" matches object whose docstring matches "ansi".
    ''')

    def title(self) -> str:
        return 'Help'
    
    @renderer
    def heading(self, request: object, tag: Tag) -> Tag:
        return tag.clear()("Help")

    @renderer
    def helpcontent(self, request: object, tag: Tag) -> Tag:
        from pydoctor.epydoc.markup import restructuredtext, ParseError
        from pydoctor.linker import NotFoundLinker
        errs: list[ParseError] = []
        parsed = restructuredtext.parse_docstring(dedent(self.RST_SOURCE_TEMPLATE.substitute(
            kind_names=', '.join(f'"{k.name}"' for k in model.DocumentableKind)
        )), errs)
        assert not errs
        return parsed.to_stan(NotFoundLinker())

def summaryPages(system: model.System) -> Iterable[Type[Page]]:
    pages: list[type[Page]] = [
        ModuleIndexPage,
        ClassIndexPage,
        NameIndexPage,
        UndocumentedSummaryPage,
        HelpPage, 
    ]
    if len(system.root_names) > 1:
        pages.append(IndexPage)
    return pages
