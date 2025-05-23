"""The classes that turn  L{Documentable} instances into objects we can render."""
from __future__ import annotations

from typing import (
    TYPE_CHECKING, Dict, Iterator, List, Optional, Mapping, Sequence,
    Type, Union
)
import ast
import abc
from urllib.parse import urljoin

from twisted.web.iweb import IRenderable, ITemplateLoader, IRequest
from twisted.web.template import Element, Tag, renderer, tags, CharRef
from pydoctor.extensions import zopeinterface

from pydoctor import epydoc2stan, model, __version__
from pydoctor.astbuilder import node2fullname
from pydoctor.templatewriter import util, TemplateLookup, TemplateElement
from pydoctor.templatewriter.pages.table import ChildTable
from pydoctor.templatewriter.pages.sidebar import SideBar
from pydoctor.epydoc.markup._pyval_repr import colorize_inline_pyval

if TYPE_CHECKING:
    from typing_extensions import Final
    from twisted.web.template import Flattenable
    from pydoctor.templatewriter.pages.attributechild import AttributeChild
    from pydoctor.templatewriter.pages.functionchild import FunctionChild


def _format_decorators(obj: Union[model.Function, model.Attribute, model.FunctionOverload]) -> Iterator["Flattenable"]:
    # Since we use this function to colorize the FunctionOverload decorators and it's not an actual Documentable subclass, we use the overload's 
    # primary function for parts that requires an interface to Documentable methods or attributes
    documentable_obj = obj if not isinstance(obj, model.FunctionOverload) else obj.primary

    for dec in obj.decorators or ():
        if isinstance(dec, ast.Call):
            fn = node2fullname(dec.func, documentable_obj)
            # We don't want to show the deprecated decorator;
            # it shows up as an infobox.
            # TODO: move this somewhere it can be customized.
            if fn in ("twisted.python.deprecate.deprecated",
                      "twisted.python.deprecate.deprecatedProperty"):
                break

        # Colorize decorators!
        doc = colorize_inline_pyval(dec)
        stan = epydoc2stan.safe_to_stan(doc, documentable_obj.docstring_linker, documentable_obj,
            fallback=epydoc2stan.colorized_pyval_fallback, 
            section='rendering of decorators')
        
        # Report eventual warnings. It warns when we can't colorize the expression for some reason.
        epydoc2stan.reportWarnings(documentable_obj, doc.warnings, section='colorize decorator')
        
        yield tags.span('@', stan.children, tags.br(), class_='decorator')

def format_decorators(obj: Union[model.Function, model.Attribute, model.FunctionOverload]) -> Tag:
    if decs:=list(_format_decorators(obj)):
        return tags.div(decs)
    return tags.transparent

def format_signature(func: Union[model.Function, model.FunctionOverload]) -> "Flattenable":
    """
    Return a stan representation of a nicely-formatted source-like function signature for the given L{Function}.
    Arguments default values are linked to the appropriate objects when possible.
    """

    parsed_sig = epydoc2stan.get_parsed_signature(func)
    if parsed_sig is None:
        return "(...)"
    ctx = func.primary if isinstance(func, model.FunctionOverload) else func
    return epydoc2stan.safe_to_stan(
        parsed_sig, 
        ctx.docstring_linker, 
        ctx, 
        fallback=lambda _, doc, ___: tags.transparent(doc.to_text()),
        section='signature'
    )

def format_class_signature(cls: model.Class) -> "Flattenable":
    """
    The class signature is the formatted list of bases this class extends. 
    It's not the class constructor.
    """
    r: List["Flattenable"] = []
    # the linker will only be used to resolve the generic arguments of the base classes, 
    # it won't actually resolve the base classes (see comment few lines below).
    # this is why we're using the annotation linker.
    _linker = cls.docstring_linker
    if cls.rawbases:
        r.append('(')
        
        for idx, ((str_base, base_node), base_obj) in enumerate(zip(cls.rawbases, cls.baseobjects)):
            if idx != 0:
                r.append(', ')

            # Make sure we bypass the linker’s resolver process for base object, 
            # because it has been resolved already (with two passes).
            # Otherwise, since the class declaration wins over the imported names,
            # a class with the same name as a base class confused pydoctor and it would link 
            # to it self: https://github.com/twisted/pydoctor/issues/662

            refmap = None
            if base_obj is not None:
                refmap = {str_base:base_obj.fullName()}
                
            # link to external class, using the colorizer here
            # to link to classes with generics (subscripts and other AST expr).
            # we use is_annotation=True because bases are unstringed, they can contain annotations. 
            stan = epydoc2stan.safe_to_stan(colorize_inline_pyval(base_node, refmap=refmap, is_annotation=True), _linker, cls, 
                fallback=epydoc2stan.colorized_pyval_fallback, 
                section='rendering of class signature')
            r.extend(stan.children)
                
        r.append(')')
    return r

LONG_SIGNATURE = 88 # this doesn't acount for the 'def ' and the ending ':'
"""
Maximum size of a function definition to be rendered on a single line. 
The multiline formatting is only applied at the CSS level to stay customizable. 
We add a css class to the signature HTML to signify the signature could possibly
be better formatted on several lines.
"""
def format_overloads(func: model.Function) -> Iterator["Flattenable"]:
    """
    Format a function overloads definitions as nice HTML signatures.
    """

    for overload in func.overloads:
        yield tags.div(format_decorators(overload), 
            tags.div(format_function_def(func.name, func.is_async, overload)),   
            class_='function-overload')

_nbsp = CharRef(160) # non-breaking space.
def format_function_def(func_name: str, is_async: bool, 
                        func: Union[model.Function, model.FunctionOverload]) -> List["Flattenable"]:
    """
    Format a function definition as nice HTML signature. 
    
    If the function is overloaded, it will return an empty list. 
    We use L{format_overloads} for these.
    """
    r:List["Flattenable"] = []
    # If this is a function with overloads, we do not render the principal 
    # signature because the overloaded signatures will be shown instead.
    if isinstance(func, model.Function) and func.overloads:
        return r
    def_stmt = ['async', _nbsp, 'def'] if is_async else ['def']
    if func_name.endswith('.setter') or func_name.endswith('.deleter'):
        func_name = func_name[:func_name.rindex('.')]
    
    func_signature_css_class = 'function-signature'
    
    # We never mark the overloaded functions as long since this could make the output of pydoctor
    # worst that before when there are many overloads to be wrapped. It allows to
    # to scroll less to get to the actual main documentation of the function.
    if not isinstance(func, model.FunctionOverload) and \
        epydoc2stan.function_signature_len(func) > LONG_SIGNATURE:
        func_signature_css_class += ' long-signature'
    
    r.extend([
        tags.span(def_stmt, class_='py-keyword'), _nbsp,
        tags.span(func_name, class_='py-defname'), 
        tags.span(format_signature(func), ':', 
                  class_=func_signature_css_class),
    ])
    return r
    

class Nav(TemplateElement):
    """
    Common navigation header.
    """

    filename = 'nav.html'

class Head(TemplateElement):
    """
    Common metadata.
    """

    filename = 'head.html'

    def __init__(self, title: str, baseurl: str | None, pageurl: str, 
                 loader: ITemplateLoader) -> None:
        super().__init__(loader)
        self._title = title
        self._baseurl = baseurl
        self._pageurl = pageurl
    
    @renderer
    def canonicalurl(self, request: IRequest, tag: Tag) -> Flattenable:
        if not self._baseurl:
            return ''
        canonical_link = urljoin(self._baseurl, self._pageurl)
        return tags.link(rel='canonical', href=canonical_link)

    @renderer
    def title(self, request: IRequest, tag: Tag) -> str:
        return self._title


class Page(TemplateElement):
    """
    Abstract base class for output pages.

    Defines special HTML placeholders that are designed to be overriden by users:
    "header.html", "subheader.html" and "footer.html".
    """

    def __init__(self, system: model.System,
                 template_lookup: TemplateLookup,
                 loader: Optional[ITemplateLoader] = None):
        self.system = system
        self.template_lookup = template_lookup
        if not loader:
            loader = self.lookup_loader(template_lookup)
        super().__init__(loader)
    
    @property
    def page_url(self) -> str:
        # This MUST be overriden in CommonPage
        """
        The relative page url
        """
        return self.filename

    def render(self, request: Optional[IRequest]) -> Tag:
        return tags.transparent(super().render(request)).fillSlots(**self.slot_map)

    @property
    def slot_map(self) -> Dict[str, "Flattenable"]:
        system = self.system

        if system.options.projecturl:
            project_tag = tags.a(href=system.options.projecturl, class_="projecthome")
        else:
            project_tag = tags.transparent
        project_tag(system.projectname)

        return dict(
            project=project_tag,
            pydoctor_version=__version__,
            buildtime=system.buildtime.strftime("%Y-%m-%d %H:%M:%S"),
        )

    @abc.abstractmethod
    def title(self) -> str:
        raise NotImplementedError()

    @renderer
    def head(self, request: IRequest, tag: Tag) -> IRenderable:
        return Head(self.title(), self.system.options.htmlbaseurl, self.page_url, 
                    loader=Head.lookup_loader(self.template_lookup))

    @renderer
    def nav(self, request: IRequest, tag: Tag) -> IRenderable:
        return Nav(Nav.lookup_loader(self.template_lookup))

    @renderer
    def header(self, request: IRequest, tag: Tag) -> IRenderable:
        return Element(self.template_lookup.get_loader('header.html'))

    @renderer
    def subheader(self, request: IRequest, tag: Tag) -> IRenderable:
        return Element(self.template_lookup.get_loader('subheader.html'))

    @renderer
    def footer(self, request: IRequest, tag: Tag) -> IRenderable:
        return Element(self.template_lookup.get_loader('footer.html'))


class CommonPage(Page):

    filename = 'common.html'
    ob: model.Documentable

    def __init__(self, ob: model.Documentable, template_lookup: TemplateLookup, docgetter: Optional[util.DocGetter]=None):
        super().__init__(ob.system, template_lookup)
        self.ob = ob
        if docgetter is None:
            docgetter = util.DocGetter()
        self.docgetter = docgetter
        self._order = ob.system.membersOrder(ob)

    @property
    def page_url(self) -> str:
        return self.ob.page_object.url

    def title(self) -> str:
        return self.ob.fullName()

    def heading(self) -> Tag:
        return tags.h1(class_=util.css_class(self.ob))(
            tags.code(self.namespace(self.ob))
            )

    def category(self) -> str:
        kind = self.ob.kind
        assert kind is not None
        return f"{epydoc2stan.format_kind(kind).lower()} documentation"

    def namespace(self, obj: model.Documentable) -> List[Union[Tag, str]]:
        page_url = self.page_url
        parts: List[Union[Tag, str]] = []
        ob: Optional[model.Documentable] = obj
        while ob:
            if ob.documentation_location is model.DocLocation.OWN_PAGE:
                if parts:
                    parts.extend(['.', tags.wbr])
                parts.append(tags.code(epydoc2stan.taglink(ob, page_url, ob.name)))
            ob = ob.parent
        parts.reverse()
        return parts
    
    @renderer
    def inhierarchy(self, request: object, tag: Tag) -> "Flattenable":
        return ()

    def extras(self) -> List["Flattenable"]:
        return self.objectExtras(self.ob)

    def docstring(self) -> "Flattenable":
        return self.docgetter.get(self.ob)

    def children(self) -> Sequence[model.Documentable]:
        return sorted(
            (o for o in self.ob.contents.values() if o.isVisible),
            key=self._order)

    def packageInitTable(self) -> "Flattenable":
        return ()

    @renderer
    def baseTables(self, request: object, tag: Tag) -> "Flattenable":
        return ()

    def mainTable(self) -> "Flattenable":
        children = self.children()
        if children:
            return ChildTable(self.docgetter, self.ob, children,
                    ChildTable.lookup_loader(self.template_lookup))
        else:
            return ()

    def methods(self) -> Sequence[model.Documentable]:
        return sorted((o for o in self.ob.contents.values()
                       if o.documentation_location is model.DocLocation.PARENT_PAGE and o.isVisible), 
                      key=self._order)

    def childlist(self) -> List[Union["AttributeChild", "FunctionChild"]]:
        from pydoctor.templatewriter.pages.attributechild import AttributeChild
        from pydoctor.templatewriter.pages.functionchild import FunctionChild

        r: List[Union["AttributeChild", "FunctionChild"]] = []

        func_loader = FunctionChild.lookup_loader(self.template_lookup)
        attr_loader = AttributeChild.lookup_loader(self.template_lookup)

        for c in self.methods():
            if isinstance(c, model.Function):
                r.append(FunctionChild(self.docgetter, c, self.objectExtras(c), func_loader))
            elif isinstance(c, model.Attribute):
                r.append(AttributeChild(self.docgetter, c, self.objectExtras(c), attr_loader))
            else:
                assert False, type(c)
        return r

    def objectExtras(self, ob: model.Documentable) -> List["Flattenable"]:
        """
        Flatten each L{model.Documentable.extra_info} list item.
        """
        r: List["Flattenable"] = []
        for extra in ob.extra_info:
            r.append(epydoc2stan.unwrap_docstring_stan(
                epydoc2stan.safe_to_stan(extra, ob.docstring_linker, ob,
                fallback = lambda _,__,___:epydoc2stan.BROKEN, section='extra')))
        return r


    def functionBody(self, ob: model.Documentable) -> "Flattenable":
        return self.docgetter.get(ob)

    @renderer
    def maindivclass(self, request: IRequest, tag: Tag) -> str:
        return 'nosidebar' if self.ob.system.options.nosidebar else ''

    @renderer
    def sidebarcontainer(self, request: IRequest, tag: Tag) -> Union[Tag, str]:
        if self.ob.system.options.nosidebar:
            return ""
        else:
            return tag.fillSlots(sidebar=SideBar(ob=self.ob, template_lookup=self.template_lookup))

    @property
    def slot_map(self) -> Dict[str, "Flattenable"]:
        slot_map = super().slot_map
        slot_map.update(
            heading=self.heading(),
            category=self.category(),
            extras=self.extras(),
            docstring=self.docstring(),
            mainTable=self.mainTable(),
            packageInitTable=self.packageInitTable(),
            childlist=self.childlist(),
        )
        return slot_map

def source_tag(href: str) -> Tag: 
    return tags.a("(source)", href=href, class_="sourceLink")

class ModulePage(CommonPage):
    ob: model.Module

    def source_links(self) -> Flattenable | None:
        if sourceHref:=util.srclink(self.ob):
            return source_tag(sourceHref)
        return None

    def extras(self) -> List["Flattenable"]:
        r: List["Flattenable"] = []
        if links:=self.source_links():
            r.append(links)
        r.extend(super().extras())
        return r


class PackagePage(ModulePage):
    ob: model.Package

    def children(self) -> Sequence[model.Documentable]:
        return sorted(self.ob.submodules(), key=self._order)

    def packageInitTable(self) -> "Flattenable":
        children = sorted(
            (o for o in self.ob.contents.values()
             if not isinstance(o, model.Module) and o.isVisible),
            key=self._order)
        if children:
            loader = ChildTable.lookup_loader(self.template_lookup)
            return [
                tags.p("From ", tags.code("__init__.py"), ":", class_="fromInitPy"),
                ChildTable(self.docgetter, self.ob, children, loader)
                ]
        else:
            return ()
    
    def source_links(self) -> Flattenable | None:
        # supports multiple source links, since there could be multiple source paths
        # for namespace packages
        links = util.package_srclinks(self.ob)
        links_max_index = len(links) - 1
        if links_max_index == -1:
            return None
        r: list[Flattenable] = []
        for i, href in enumerate(links):
            r.append(source_tag(href))
            if 0 <= i < links_max_index:
                r.append(', ')
        return tags.transparent(*r)

    def methods(self) -> Sequence[model.Documentable]:
        return sorted([o for o in self.ob.contents.values()
                if o.documentation_location is model.DocLocation.PARENT_PAGE
                and o.isVisible], key=self._order)

def assembleList(
        system: model.System,
        label: str,
        lst: Sequence[str],
        page_url: str
        ) -> Optional["Flattenable"]:
    """
    Convert list of object names into a stan tree with clickable links. 
    """
    lst2 = []
    for name in lst:
        o = system.allobjects.get(name)
        if o is None or o.isVisible:
            lst2.append(name)
    lst = lst2
    if not lst:
        return None
    def one(item: str) -> "Flattenable":
        if item in system.allobjects:
            return tags.code(epydoc2stan.taglink(system.allobjects[item], page_url))
        else:
            return item
    def commasep(items: Sequence[str]) -> List["Flattenable"]:
        r = []
        for item in items:
            r.append(one(item))
            r.append(', ')
        del r[-1]
        return r
    p: List["Flattenable"] = [label]
    p.extend(commasep(lst))
    return p


class ClassPage(CommonPage):

    ob: model.Class

    def __init__(self,
            ob: model.Documentable,
            template_lookup: TemplateLookup,
            docgetter: Optional[util.DocGetter] = None
            ):
        super().__init__(ob, template_lookup, docgetter)
        self.baselists = util.class_members(self.ob)

    def extras(self) -> List["Flattenable"]:
        r: List["Flattenable"] = []

        sourceHref = util.srclink(self.ob)
        source: "Flattenable"
        if sourceHref:
            source = (" ", tags.a("(source)", href=sourceHref, class_="sourceLink"))
        else:
            source = tags.transparent
        r.append(tags.p(tags.code(
            tags.span("class", class_='py-keyword'), " ",
            tags.span(self.ob.name, class_='py-defname'),
            self.classSignature(), ":", source
            ), class_='class-signature'))

        subclasses = sorted(self.ob.subclasses, key=util.alphabetical_order_func)
        if subclasses:
            p = assembleList(self.ob.system, "Known subclasses: ",
                            [o.fullName() for o in subclasses], self.page_url)
            if p is not None:
                r.append(tags.p(p))

        constructor = epydoc2stan.get_constructors_extra(self.ob)
        if constructor:
            r.append(epydoc2stan.unwrap_docstring_stan(
                epydoc2stan.safe_to_stan(constructor, self.ob.docstring_linker, self.ob,
                fallback = lambda _,__,___:epydoc2stan.BROKEN, section='constructor extra')))

        r.extend(super().extras())
        return r

    def classSignature(self) -> "Flattenable":
        return format_class_signature(self.ob)

    @renderer
    def inhierarchy(self, request: object, tag: Tag) -> Tag:
        return tag(href="classIndex.html#"+self.ob.fullName())

    @renderer
    def baseTables(self, request: object, item: Tag) -> "Flattenable":
        baselists = self.baselists[:]
        if not baselists:
            return []
        if baselists[0][0][0] == self.ob:
            del baselists[0]
        loader = ChildTable.lookup_loader(self.template_lookup)
        return [item.clone().fillSlots(
                          baseName=self.baseName(b),
                          baseTable=ChildTable(self.docgetter, self.ob,
                                               sorted(attrs, key=self._order),
                                               loader))
                for b, attrs in baselists]

    def baseName(self, bases: Sequence[model.Class]) -> "Flattenable":
        page_url = self.page_url
        r: List["Flattenable"] = []
        source_base = bases[0]
        r.append(tags.code(epydoc2stan.taglink(source_base, page_url, source_base.name)))
        bases_to_mention = bases[1:-1]
        if bases_to_mention:
            tail: List["Flattenable"] = []
            for b in reversed(bases_to_mention):
                tail.append(tags.code(epydoc2stan.taglink(b, page_url, b.name)))
                tail.append(', ')
            del tail[-1]
            r.extend([' (via ', tail, ')'])
        return r

    def objectExtras(self, ob: model.Documentable) -> List["Flattenable"]:
        r: List["Flattenable"] = list(get_override_info(self.ob, ob.name, self.page_url))
        r.extend(super().objectExtras(ob))
        return r

def get_override_info(cls:model.Class, member_name:str, page_url:Optional[str]=None) -> Iterator["Flattenable"]:
    page_url = page_url or cls.page_object.url
    for b in cls.mro(include_self=False):
        if member_name not in b.contents:
            continue
        overridden = b.contents[member_name]
        yield tags.div(class_="interfaceinfo")(
            'overrides ', tags.code(epydoc2stan.taglink(overridden, page_url)))
        break
    
    ocs = sorted(util.overriding_subclasses(cls, member_name), key=util.alphabetical_order_func)
    if ocs:
        l = assembleList(cls.system, 'overridden in ',
                            [o.fullName() for o in ocs], page_url)
        if l is not None:
            yield tags.div(class_="interfaceinfo")(l)
    

class ZopeInterfaceClassPage(ClassPage):
    ob: zopeinterface.ZopeInterfaceClass

    def extras(self) -> List["Flattenable"]:
        r = super().extras()
        if self.ob.isinterface:
            namelist = [o.fullName() for o in 
                        sorted(self.ob.implementedby_directly, key=util.alphabetical_order_func)]
            label = 'Known implementations: '
        else:
            namelist = sorted(self.ob.implements_directly, key=lambda x:x.lower())
            label = 'Implements interfaces: '
        if namelist:
            l = assembleList(self.ob.system, label, namelist, self.page_url)
            if l is not None:
                r.append(tags.p(l))
        return r

    def interfaceMeth(self, methname: str) -> Optional[model.Documentable]:
        system = self.ob.system
        for interface in self.ob.allImplementedInterfaces:
            if interface in system.allobjects:
                io = system.allobjects[interface]
                assert isinstance(io, zopeinterface.ZopeInterfaceClass)
                for io2 in io.mro():
                    method: Optional[model.Documentable] = io2.contents.get(methname)
                    if method is not None:
                        return method
        return None

    def objectExtras(self, ob: model.Documentable) -> List["Flattenable"]:
        imeth = self.interfaceMeth(ob.name)
        r: List["Flattenable"] = []
        if imeth:
            iface = imeth.parent
            assert iface is not None
            r.append(tags.div(class_="interfaceinfo")('from ', tags.code(
                epydoc2stan.taglink(imeth, self.page_url, iface.fullName())
                )))
        r.extend(super().objectExtras(ob))
        return r

commonpages: 'Final[Mapping[str, Type[CommonPage]]]' = {
    'Module': ModulePage,
    'Package': PackagePage,
    'Class': ClassPage,
    'ZopeInterfaceClass': ZopeInterfaceClassPage,
}
"""List all page classes: ties documentable class name with the page class used for rendering"""
